from datetime import UTC, datetime
from statistics import median
from time import perf_counter
from uuid import UUID, uuid4, uuid5

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from langsmith import tracing_context
from sqlalchemy import text

from agentflow.advisor import ModelAdvisor
from agentflow.audit import EvidenceError, verify
from agentflow.config import DATASET_VERSION, DEMO_LABEL, conninfo
from agentflow.domain import BenchmarkCase, Evidence, Mode, Plan, Report, Strategy
from agentflow.judge import score_report
from agentflow.models import (
    MAX_OUTPUT,
    MAX_STEPS,
    PROMPT_VERSION,
    SYSTEMS,
    LangSmithExport,
    ModelFailure,
    OllamaClient,
)
from agentflow.reporting import LIMITATION, verify_citations
from agentflow.store import Problem, Row, Store, encode
from agentflow.transport import MCPClient
from agentflow.workflow import build_graph

TOOL_BUDGET = 24  # Nine calls, plus at most one transport retry per specialist.


def _provenance(report: Report, evidence: dict[str, Evidence]) -> bool:
    try:
        verify_citations(report, evidence)
        return all(row.id == row.content_id() for row in evidence.values())
    except EvidenceError:
        return False


def grade(
    case: BenchmarkCase,
    report: Report,
    evidence: dict[str, Evidence],
    plan: Plan,
    approved_after_gate: bool,
    attempts: int,
    denied: int,
) -> dict[str, bool | None]:
    gold = case.gold
    sources = {source.id for ev in evidence.values() for source in ev.sources}
    comparison = report.comparison
    numeric = None
    if gold.before is not None:
        numeric = bool(
            comparison
            and (comparison.baseline.checkout_starts, comparison.baseline.purchases) == gold.before
            and (comparison.current.checkout_starts, comparison.current.purchases) == gold.after
            and comparison.delta == gold.delta_pp
        )
    scoped = report.scope == case.scenario.scope and set(plan.domains) == set(case.domains)
    try:
        verify(plan, case.scenario.scope, evidence)
    except EvidenceError:
        scoped = False
    return {
        "arithmetic": numeric,
        "provenance": _provenance(report, evidence) and set(gold.source_ids) <= sources,
        "scope": scoped,
        "key_finding": report.hypothesis == gold.hypothesis,
        "uncertainty": (not gold.uncertainty or LIMITATION in report.limitations)
        and (
            gold.hypothesis
            not in {
                "missing_data",
                "low_volume",
                "undetermined",
                "ambiguous_timeline",
                "conflicting_signals",
            }
            or report.confidence == "limited"
        ),
        "tool_boundary": denied == 0 and 0 < attempts <= TOOL_BUDGET,
        "approval_gate": approved_after_gate,
    }


class Benchmarks:
    def __init__(
        self,
        store: Store,
        client: MCPClient,
        cases: dict[str, BenchmarkCase],
        ollama: OllamaClient,
        traces: LangSmithExport,
    ) -> None:
        self.store = store
        self.client = client
        self.cases = cases
        self.ollama = ollama
        self.traces = traces

    def create(self, strategy: str, mode: Mode, model: str | None, judge_model: str | None) -> UUID:
        with self.store.engine.begin() as connection:
            job_id = uuid4()
            connection.execute(
                text(
                    """INSERT INTO evaluations (id,strategy,mode,model,judge_model,dataset_version,status)
                   VALUES (:id,:strategy,:mode,:model,:judge,:version,'queued')"""
                ),
                {
                    "id": job_id,
                    "strategy": strategy,
                    "mode": mode,
                    "model": model,
                    "judge": judge_model,
                    "version": DATASET_VERSION,
                },
            )
        return job_id

    def get(self, job_id: UUID) -> Row:
        job = self.store.one("SELECT * FROM evaluations WHERE id=:id", {"id": job_id})
        if job is None:
            raise Problem("evaluation_not_found", "Evaluation could not be found.", 404)
        results = [
            row["result"]
            for row in self.store.all(
                """SELECT result FROM evaluation_cases WHERE evaluation_id=:id ORDER BY scenario_id,strategy""",
                {"id": job_id},
            )
        ]
        job["cases"] = results
        job["total_cases"] = (
            len(results)
            if job["status"] == "completed"
            else (12 if job["dataset_version"] == "northstar-1" else len(self.cases))
            * (2 if job["strategy"] == "compare" else 1)
        )
        summaries = {}
        for strategy in ("single", "multi"):
            line = [case for case in results if case["strategy"] == strategy]
            if line:
                holdout = [case for case in line if case.get("suite") == "holdout"]
                summaries[strategy] = {
                    "holdout_completed": len(holdout),
                    "holdout_passed": sum(case["passed"] for case in holdout),
                    "completed": len(line),
                    "passed": sum(case["passed"] for case in line),
                    "median_duration_ms": round(median(case["duration_ms"] for case in line), 1),
                    "tool_calls": sum(case["tool_calls"] for case in line),
                }
        job["summaries"] = summaries
        return job

    def step(self) -> bool:
        job = self.store.one("""SELECT * FROM evaluations WHERE status IN ('queued','running')
                             ORDER BY created_at LIMIT 1""")
        if not job:
            return False
        job_id = job["id"]
        with self.store.engine.begin() as connection:
            connection.execute(
                text("UPDATE evaluations SET status='running' WHERE id=:id"), {"id": job_id}
            )
        done = {
            (row["scenario_id"], row["strategy"])
            for row in self.store.all(
                "SELECT scenario_id,strategy FROM evaluation_cases WHERE evaluation_id=:id",
                {"id": job_id},
            )
        }
        for index, (case_id, case) in enumerate(self.cases.items()):
            strategies: tuple[Strategy, Strategy] = (
                ("single", "multi") if index % 2 == 0 else ("multi", "single")
            )
            for strategy in strategies:
                if job["strategy"] not in ("compare", strategy) or (case_id, strategy) in done:
                    continue
                result = self.run_case(job, case, strategy)
                with self.store.engine.begin() as connection:
                    connection.execute(
                        text("""INSERT INTO evaluation_cases
                        (evaluation_id,scenario_id,strategy,result) VALUES (:id,:case,:strategy,CAST(:result AS jsonb))
                        ON CONFLICT DO NOTHING"""),
                        {
                            "id": job_id,
                            "case": case_id,
                            "strategy": strategy,
                            "result": encode(result),
                        },
                    )
                return True
        with self.store.engine.begin() as connection:
            connection.execute(
                text("UPDATE evaluations SET status='completed',completed_at=now() WHERE id=:id"),
                {"id": job_id},
            )
        return True

    def run_case(self, job: Row, case: BenchmarkCase, strategy: Strategy) -> Row:
        scenario = case.scenario
        started = datetime.now(UTC)
        tick = perf_counter()
        recorded: list[tuple[str, str, Row]] = []
        thread_id = str(uuid5(job["id"], f"{scenario.id}:{strategy}"))
        config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 18,
        }
        result: Row = {
            "scenario_id": scenario.id,
            "title": scenario.title,
            "strategy": strategy,
            "mode": job["mode"],
            "mode_label": DEMO_LABEL
            if job["mode"] == "demo"
            else {
                "ollama": "Live local Ollama",
                "openai": "Live OpenAI",
                "anthropic": "Live Claude",
            }[job["mode"]],
            "version": scenario.version,
            "suite": scenario.suite,
            "task_hash": scenario.task_hash,
            "model": job["model"],
            "started_at": started.isoformat(),
            "prompts": {
                "version": PROMPT_VERSION,
                "templates": SYSTEMS,
                "steps": MAX_STEPS,
                "output_tokens_per_call": MAX_OUTPUT,
            }
            if job["model"]
            else None,
            "question": scenario.question,
            "tool_budget": TOOL_BUDGET,
            "token_count": None,
            "passed": False,
            "expected": case.gold.model_dump(mode="json"),
            "checks": {},
            "observed": None,
            "error": None,
        }

        def log(node: str, kind: str, detail: Row) -> None:
            recorded.append((node, kind, detail))

        try:
            with (
                tracing_context(enabled=False),
                PostgresSaver.from_conn_string(conninfo(checkpoints=True)) as saver,
            ):
                saver.delete_thread(thread_id)
                try:
                    advisor = (
                        ModelAdvisor(self.ollama.settings, job["mode"], job["model"], log)
                        if job["model"]
                        else None
                    )
                    graph = build_graph(self.client, saver, log, advisor)
                    graph.invoke(
                        {
                            "scenario": scenario.model_dump(mode="json"),
                            "question": scenario.question,
                            "mode": job["mode"],
                            "model": job["model"],
                            "strategy": strategy,
                            "review_round": 1,
                        },
                        config,
                        durability="sync",
                    )
                    state = graph.get_state(config)
                    if not state.interrupts:
                        raise ModelFailure("The planner reached no reviewable checkpoint.")
                    gate = state.interrupts[0]
                    passed_gate = len(state.interrupts) == 1 and not state.values.get("result")
                    report = Report.model_validate(state.values["draft"])
                    evidence = {
                        key: Evidence.model_validate(value)
                        for key, value in state.values["evidence"].items()
                    }
                    plan = Plan.model_validate(state.values["plan"])
                    # This approval tests the graph in a benchmark thread; it creates no user report.
                    graph.invoke(
                        Command(
                            resume={
                                "interrupt_id": gate.id,
                                "round": gate.value["round"],
                                "action": "approve",
                                "note": "Benchmark fixture approval",
                            }
                        ),
                        config,
                        durability="sync",
                    )
                    final = graph.get_state(config)
                    approved = (
                        passed_gate
                        and not final.interrupts
                        and final.values.get("result") == "approved"
                    )
                    checks = grade(
                        case,
                        report,
                        evidence,
                        plan,
                        approved,
                        sum(kind in {"tool_finished", "tool_failed"} for _, kind, _ in recorded),
                        sum(kind == "tool_denied" for _, kind, _ in recorded),
                    )
                    result.update(
                        checks=checks,
                        passed=all(value for value in checks.values() if value is not None),
                        observed={
                            "hypothesis": report.hypothesis,
                            "delta_pp": report.comparison.delta if report.comparison else None,
                            "confidence": report.confidence,
                            "evidence_ids": sorted(entry.id for entry in evidence.values()),
                        },
                    )
                finally:
                    saver.delete_thread(thread_id)
        except ModelFailure as exc:
            result["error"] = str(exc)
        except Exception as exc:
            result["error"] = f"Scenario execution failed ({type(exc).__name__})."
        result["duration_ms"] = round((perf_counter() - tick) * 1000, 1)
        model_calls = [
            detail for _, kind, detail in recorded if kind in {"model_finished", "model_failed"}
        ]
        if model_calls and all(
            "eval_count" in row and "prompt_eval_count" in row for row in model_calls
        ):
            result["token_count"] = sum(
                row["eval_count"] + row["prompt_eval_count"] for row in model_calls
            )
        if job["judge_model"] and result["observed"]:
            result["judge"] = score_report(self.ollama, job["judge_model"], report, evidence, log)
        self.traces.send(
            "agentflow.evaluation-case",
            started,
            {
                "evaluation_id": str(job["id"]),
                "scenario_id": scenario.id,
                "strategy": strategy,
                "mode": job["mode"],
                "model": job["model"],
                "passed": result["passed"],
            },
            log,
        )
        result["trace_delivery"] = next(
            (kind for _, kind, _ in reversed(recorded) if kind.startswith("trace_export")), None
        )
        result["tool_calls"] = sum(
            kind in {"tool_finished", "tool_failed"} for _, kind, _ in recorded
        )
        return result
