import hashlib
import json
from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agentflow.config import DATASET_VERSION, ROOT

Segment = Literal["all", "mobile", "web"]
Domain = Literal["metrics", "timeline", "support"]
DOMAINS: tuple[Domain, ...] = ("metrics", "timeline", "support")
Mode = Literal["demo", "ollama", "openai", "anthropic"]
Strategy = Literal["single", "multi"]
ReviewAction = Literal["approve", "reject", "revise"]
Hypothesis = Literal[
    "missing_data",
    "low_volume",
    "conflicting_signals",
    "traffic_drop",
    "stable",
    "mix_shift",
    "timing_conflict",
    "ambiguous_timeline",
    "payment_regression",
    "undetermined",
    "support_signal",
    "support_limited",
    "timeline_only",
]
RunStatus = Literal[
    "queued",
    "running",
    "awaiting_review",
    "review_queued",
    "reviewing",
    "approved",
    "rejected",
    "failed",
    "canceled",
    "needs_clarification",
]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


class Window(Model):
    start: date
    end: date

    @model_validator(mode="after")
    def validate_span(self) -> "Window":
        if not date(2025, 10, 1) <= self.start <= self.end <= date(2026, 1, 31):
            raise ValueError("Choose an ordered window from October 2025 through January 2026.")
        if (self.end - self.start).days >= 14:
            raise ValueError("A tool window may include up to 14 UTC days.")
        return self

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


class Scope(Model):
    day: date
    segment: Segment
    baseline: Window
    current: Window

    @property
    def full(self) -> Window:
        return Window(start=self.baseline.start, end=self.current.end)


class Scenario(Model):
    id: str
    version: int
    title: str
    description: str
    question: str
    scope: Scope
    task_hash: str
    suite: Literal["development", "holdout"] = "development"


class Gold(Model):
    hypothesis: Hypothesis
    before: tuple[int, int] | None = None
    after: tuple[int, int] | None = None
    delta_pp: float | None = None
    source_ids: list[str]
    uncertainty: bool


class BenchmarkCase(Model):
    scenario: Scenario
    domains: list[Domain]
    gold: Gold


def load_cases() -> dict[str, BenchmarkCase]:
    cases: dict[str, BenchmarkCase] = {}
    rows: list[dict[str, Any]] = []
    for filename, suite in (
        ("scenarios.json", "development"),
        ("holdout-scenarios.json", "holdout"),
    ):
        rows.extend(
            {**row, "suite": suite}
            for row in json.loads((ROOT / "eval" / filename).read_text(encoding="utf-8"))
        )
    for row in rows:
        day = date.fromisoformat(row["day"])
        scope = Scope(
            day=day,
            segment=row["segment"],
            baseline=Window(start=day - timedelta(days=3), end=day - timedelta(days=1)),
            current=Window(start=day, end=day + timedelta(days=2)),
        )
        scenario = Scenario(
            suite=row["suite"],
            id=row["id"],
            version=row["version"],
            title=row["title"],
            description=row["description"],
            question=row["question"],
            scope=scope,
            task_hash=digest({"dataset_version": DATASET_VERSION, "case": row}),
        )
        if scenario.id in cases:
            raise ValueError(f"Duplicate scenario ID {scenario.id}")
        cases[scenario.id] = BenchmarkCase(
            scenario=scenario, domains=row["domains"], gold=row["gold"]
        )
    return cases


class Plan(Model):
    domains: list[Domain]
    rationale: str
    clarification: str | None = None


class MetricRequest(Model):
    window: Window
    segment: Segment = "all"


class CompareRequest(Model):
    baseline: Window
    current: Window
    segment: Segment = "all"
    metric: Literal["checkout_conversion", "sessions", "purchases"] = "checkout_conversion"

    @model_validator(mode="after")
    def validate_order(self) -> "CompareRequest":
        if self.baseline.end >= self.current.start:
            raise ValueError("The baseline must end before the current window starts.")
        return self


class TimelineRequest(Model):
    window: Window


class RecordRequest(Model):
    evidence_id: str = Field(pattern=r"^(traffic|pay|ticket|rel|flag)-[a-z0-9_-]{1,110}$")


class Source(Model):
    id: str
    table: Literal[
        "traffic_metrics", "payment_events", "support_tickets", "releases", "feature_flags"
    ]


class Evidence(Model):
    id: str
    tool: str
    request: dict[str, Any]
    sources: list[Source]
    payload: dict[str, Any]

    def content_id(self) -> str:
        return "ev-" + digest(self.model_dump(exclude={"id"}, mode="json"))[:24]


class TrafficRow(Model):
    day: date
    segment: Literal["web", "mobile"]
    sessions: int = Field(ge=0)
    checkout_starts: int = Field(ge=0)
    purchases: int = Field(ge=0)


class Totals(Model):
    sessions: int = Field(ge=0)
    checkout_starts: int = Field(ge=0)
    purchases: int = Field(ge=0)
    conversion_pct: float | None
    observed_days: int = Field(ge=0)
    complete: bool


class TrafficSummary(Model):
    totals: Totals
    rows: list[TrafficRow]


class Comparison(Model):
    baseline: Totals
    current: Totals
    delta: float | None
    unit: Literal["percentage_points", "count"]
    segments: dict[str, tuple[Totals, Totals]]


class PaymentBucket(Model):
    segment: Literal["mobile", "web"]
    method: Literal["card", "wallet"]
    outcome: Literal["approved", "declined", "authentication_timeout"]
    count: int = Field(gt=0)


class Payments(Model):
    total: int = Field(ge=0)
    failures: int = Field(ge=0)
    failure_pct: float | None
    coverage_days: int = Field(ge=0)
    complete: bool
    buckets: list[PaymentBucket]


class Tickets(Model):
    total: int = Field(ge=0)
    categories: dict[str, int]
    days_with_records: int = Field(ge=0)
    excerpts: dict[str, str]


class Release(Model):
    id: str
    version: str
    deployed_at: str
    area: str
    description: str


class Flag(Model):
    id: str
    release_id: str
    flag: str
    segment: Segment
    enabled_at: str
    rollout_percent: int = Field(ge=0, le=100)


class Releases(Model):
    records: list[Release]


class Flags(Model):
    records: list[Flag]


PAYLOADS: dict[str, type[Model]] = {
    "get_metric_summary": TrafficSummary,
    "compare_time_windows": Comparison,
    "get_payment_error_breakdown": Payments,
    "list_releases": Releases,
    "list_feature_flag_changes": Flags,
    "get_support_category_trends": Tickets,
}


class Finding(Model):
    kind: Literal["observation", "hypothesis"]
    title: str
    text: str
    evidence_ids: list[str]


class Report(Model):
    title: str
    scenario_id: str
    dataset_version: str = DATASET_VERSION
    scope: Scope
    mode: Mode
    mode_label: str
    model: str | None
    headline: str
    hypothesis: Hypothesis
    confidence: Literal["limited", "moderate"]
    findings: list[Finding]
    limitations: list[str]
    unresolved_questions: list[str]
    next_actions: list[str]
    comparison: Comparison | None = None
    review_round: int = 1
    analysis_source: Literal["rules", "model"] = "rules"
    explanations: list[dict[str, Any]] = Field(default_factory=list)


class Decision(Model):
    interrupt_id: str
    round: int
    action: ReviewAction
    note: str
