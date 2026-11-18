import logging
from datetime import UTC, datetime
from threading import Event, Thread
from time import monotonic
from uuid import UUID

import psycopg
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.types import Command
from langsmith import tracing_context
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from agentflow.advisor import ModelAdvisor
from agentflow.audit import EvidenceError
from agentflow.benchmark import Benchmarks
from agentflow.config import conninfo
from agentflow.domain import Decision, Evidence, Plan
from agentflow.judge import Calibrations
from agentflow.models import LangSmithExport, ModelFailure, OllamaClient
from agentflow.store import Problem, Row, Store
from agentflow.transport import MCPClient, ToolContractError, ToolUnavailable
from agentflow.workflow import build_graph

LOGGER = logging.getLogger(__name__)
WORKER_LOCK = 437001290


class Worker:
    def __init__(
        self,
        store: Store,
        client: MCPClient,
        benchmark: Benchmarks,
        calibrations: Calibrations,
        ollama: OllamaClient,
        traces: LangSmithExport,
    ) -> None:
        self.store = store
        self.client = client
        self.benchmark = benchmark
        self.calibrations = calibrations
        self.ollama = ollama
        self.traces = traces
        self.last_maintenance = -3600.0
        self.stop = Event()
        self.thread = Thread(target=self.run, name="agentflow-scheduler", daemon=True)

    def run(self) -> None:
        while not self.stop.is_set():
            try:
                with psycopg.connect(conninfo(), autocommit=True) as holder:
                    # This connection must stay open: the lock belongs to its PostgreSQL session.
                    # A transaction-pooling database URL cannot preserve that ownership.
                    lock = holder.execute(
                        "SELECT pg_try_advisory_lock(%s)", (WORKER_LOCK,)
                    ).fetchone()
                    if lock and lock[0]:
                        self.loop(holder)
            except (psycopg.Error, SQLAlchemyError) as exc:
                LOGGER.warning("Scheduler will reconnect (%s).", type(exc).__name__)
            self.stop.wait(1)

    def loop(self, holder: psycopg.Connection) -> None:
        while not self.stop.is_set():
            holder.execute("SELECT 1")
            if self.ollama.settings.public_demo and monotonic() - self.last_maintenance > 3600:
                self.maintain_demo()
                self.last_maintenance = monotonic()
            row = self.store.claim()
            if row:
                self.process(row)
                continue
            if not (self.benchmark.step() or self.calibrations.step()):
                self.stop.wait(0.35)

    def maintain_demo(self) -> None:
        expired = self.store.all("""SELECT id FROM investigations
            WHERE visitor_id IS NOT NULL AND created_at < now()-interval '1 day' LIMIT 500""")
        with PostgresSaver.from_conn_string(conninfo(checkpoints=True)) as saver:
            for row in expired:
                saver.delete_thread(str(row["id"]))
                with self.store.engine.begin() as connection:
                    connection.execute(
                        text("DELETE FROM investigations WHERE id=:id"), {"id": row["id"]}
                    )
            with self.store.engine.begin() as connection:
                connection.execute(
                    text("DELETE FROM visitor_limits WHERE window_start < now()-interval '1 day'")
                )
        if not self.store.one("SELECT id FROM evaluations WHERE mode='demo' LIMIT 1"):
            self.benchmark.create("compare", "demo", None, None)

    def process(self, row: Row) -> None:
        run_id: UUID = row["id"]
        started = datetime.now(UTC)

        def emit(node: str, kind: str, detail: Row) -> None:
            self.store.event(run_id, node, kind, detail)

        config: RunnableConfig = {"configurable": {"thread_id": str(run_id)}, "recursion_limit": 18}
        try:
            with (
                tracing_context(enabled=False),
                PostgresSaver.from_conn_string(conninfo(checkpoints=True)) as saver,
            ):
                advisor = (
                    ModelAdvisor(self.ollama.settings, row["mode"], row["model"], emit)
                    if row["model"]
                    else None
                )
                graph = build_graph(self.client, saver, emit, advisor)
                snapshot = graph.get_state(config)
                if snapshot.interrupts:
                    gate = snapshot.interrupts[0]
                    decision = self.store.one(
                        """SELECT interrupt_id,round,action,note FROM review_decisions
                        WHERE run_id=:id AND interrupt_id=:interrupt""",
                        {"id": run_id, "interrupt": gate.id},
                    )
                    if decision:
                        # Recovery replays the stored decision for this exact interrupt, not a new one.
                        graph.invoke(Command(resume=decision), config, durability="sync")
                elif not snapshot.values:
                    graph.invoke(
                        {
                            "scenario": row["scenario"],
                            "question": row["question"],
                            "mode": row["mode"],
                            "model": row["model"],
                            "strategy": "multi",
                            "review_round": 1,
                        },
                        config,
                        durability="sync",
                    )
                elif snapshot.next:
                    graph.invoke(None, config, durability="sync")
                snapshot = graph.get_state(config)
                values = snapshot.values
                checkpoint = snapshot.config["configurable"].get("checkpoint_id")
                evidence = [
                    Evidence.model_validate(item) for item in values.get("evidence", {}).values()
                ]
                pending = None
                decision_data = values.get("last_review")
                completed = Decision.model_validate(decision_data) if decision_data else None
                problem = None
                if snapshot.interrupts:
                    gate = snapshot.interrupts[0]
                    status = "awaiting_review"
                    pending = {"interrupt_id": gate.id, "round": gate.value["round"]}
                elif values.get("result") in ("approved", "rejected"):
                    status = values["result"]
                else:
                    plan = Plan.model_validate(values["plan"])
                    if not plan.clarification:
                        raise RuntimeError("The workflow stopped before a review checkpoint.")
                    status = "needs_clarification"
                    problem = plan.clarification
                self.store.synchronize(
                    run_id,
                    status,
                    checkpoint,
                    evidence,
                    values.get("draft"),
                    pending,
                    completed,
                    problem,
                )
                self.traces.send(
                    "agentflow.investigation",
                    started,
                    {
                        "run_id": str(run_id),
                        "scenario_id": row["scenario"]["id"],
                        "mode": row["mode"],
                        "model": row["model"],
                        "status": status,
                        "checkpoint_id": checkpoint,
                    },
                    emit,
                )
        except (psycopg.Error, SQLAlchemyError):
            # Leave the job active so the single worker can recover from its last checkpoint.
            raise
        except (ToolUnavailable, ToolContractError, EvidenceError, ModelFailure) as exc:
            self.store.fail(run_id, str(exc))
        except Problem as exc:
            if exc.code != "canceled":
                self.store.fail(run_id, exc.message)
        except Exception as exc:
            LOGGER.error("Investigation %s failed with %s", run_id, type(exc).__name__)
            self.store.fail(
                run_id, "The workflow failed. Inspect the actual run events and try a new run."
            )
