from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from agentflow.domain import Mode, Model, Report, ReviewAction, RunStatus, Scenario


class StartRequest(Model):
    model_config = ConfigDict(str_strip_whitespace=True)
    scenario_id: str = Field(min_length=1, max_length=80)
    question: str | None = Field(default=None, min_length=8, max_length=600)
    mode: Mode = "demo"


class ReviewRequest(Model):
    model_config = ConfigDict(str_strip_whitespace=True)
    interrupt_id: str = Field(min_length=1, max_length=150, pattern=r"^[a-zA-Z0-9_-]+$")
    action: ReviewAction
    note: str = Field(default="", max_length=600)

    @model_validator(mode="after")
    def feedback_required(self) -> "ReviewRequest":
        if self.action == "revise" and not self.note:
            raise ValueError("A revision requires a reviewer note.")
        return self


class Pending(Model):
    interrupt_id: str
    round: int


class ReviewView(Pending):
    action: ReviewAction
    note: str
    created_at: datetime


class RunSummary(Model):
    id: UUID
    scenario: Scenario
    question: str
    mode: Mode
    mode_label: str
    model: str | None
    status: RunStatus
    created_at: datetime
    updated_at: datetime


class RunView(RunSummary):
    checkpoint_id: str | None
    pending: Pending | None
    draft: Report | None
    error: str | None
    reviews: list[ReviewView]


class EventItem(Model):
    id: int
    occurred_at: datetime
    node: str
    kind: str
    detail: dict[str, Any]


class EventPage(Model):
    events: list[EventItem]
    next_cursor: int


class EvaluationRequest(Model):
    strategy: Literal["single", "multi", "compare"] = "compare"
    mode: Mode = "demo"
    judge: bool = False


class JobCreated(Model):
    id: UUID
    status: Literal["queued"] = "queued"


class ComponentStatus(Model):
    state: Literal["ok", "unavailable", "not_configured", "configured"]
    detail: str


class Connections(Model):
    api: ComponentStatus
    database: ComponentStatus
    mcp: ComponentStatus
    ollama: ComponentStatus
    judge: ComponentStatus
    openai: ComponentStatus
    anthropic: ComponentStatus
    langsmith: ComponentStatus
