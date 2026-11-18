"""Validated model assessments over audited facts, with independently cited alternatives."""

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Literal

from pydantic import Field

from agentflow.domain import Evidence, Finding, Hypothesis, Report
from agentflow.models import ModelFailure, StrictOutput


class SpecialistAssessment(StrictOutput):
    focus: str = Field(min_length=1, max_length=80)
    observation: str = Field(min_length=8, max_length=500)
    alternative: str = Field(min_length=8, max_length=400)
    follow_up: str = Field(max_length=40)


class Explanation(StrictOutput):
    hypothesis: Hypothesis
    title: str = Field(min_length=5, max_length=110)
    assessment: str = Field(min_length=12, max_length=650)
    supporting_evidence: list[str] = Field(min_length=1, max_length=5)
    contradicting_evidence: list[str] = Field(max_length=3)
    uncertainty: str = Field(min_length=12, max_length=450)


Qualitative = Annotated[str, Field(min_length=8, max_length=350)]


class Narrative(StrictOutput):
    explanations: list[Explanation] = Field(min_length=2, max_length=2)
    confidence: Literal["limited", "moderate"]
    next_actions: list[Qualitative] = Field(min_length=1, max_length=3)
    unresolved_questions: list[Qualitative] = Field(min_length=1, max_length=3)


def projection(evidence: dict[str, Evidence]) -> dict[str, object]:
    # This is the model trust boundary: ticket excerpts and release descriptions stay out.
    keys = (
        "totals",
        "baseline",
        "current",
        "delta",
        "unit",
        "segments",
        "buckets",
        "total",
        "failures",
        "failure_pct",
        "categories",
        "coverage_days",
        "complete",
        "observed_days",
    )
    fields = (
        "id",
        "version",
        "area",
        "deployed_at",
        "flag",
        "enabled_at",
        "rollout_percent",
        "segment",
    )
    return {
        key: {
            "evidence_id": record.id,
            "request": record.request,
            "source_count": len(record.sources),
            **{name: record.payload[name] for name in keys if name in record.payload},
            "timeline": [
                {name: row[name] for name in fields if name in row}
                for row in record.payload.get("records", [])
            ],
        }
        for key, record in evidence.items()
    }


def prose_valid(text: str) -> bool:
    # Structured citations and source-linked numerical checks complement human review.
    return not re.search(
        r"https?://|<[^>]*>|\b(proves?|proven|definitely|certainly|guaranteed)\b", text, re.I
    )


def numbers_grounded(text: str, evidence: dict[str, Evidence]) -> bool:
    # Literal matching catches invented figures; it cannot prove a claim's meaning.
    # The evidence auditor checks arithmetic, and human review checks interpretation.
    allowed: set[Decimal] = set()

    def collect(value):
        if isinstance(value, dict):
            for child in value.values():
                collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)
        elif isinstance(value, (str, int, float)):
            for token in re.findall(r"[0-9]+(?:\.[0-9]+)?", str(value).replace(",", "")):
                try:
                    number = Decimal(token)
                    allowed.update({number, abs(number), abs(round(number, 2))})
                except InvalidOperation:
                    pass

    collect(projection(evidence))
    return all(
        Decimal(token) in allowed
        for token in re.findall(r"[0-9]+(?:\.[0-9]+)?", text.replace(",", ""))
    )


def narrative_valid(value: Narrative, evidence: dict[str, Evidence]) -> bool:
    ids = {record.id for record in evidence.values()}
    prose = [*value.next_actions, *value.unresolved_questions]
    for explanation in value.explanations:
        if not set(explanation.supporting_evidence + explanation.contradicting_evidence) <= ids:
            return False
        factual_text = " ".join(
            (explanation.title, explanation.assessment, explanation.uncertainty)
        )
        cited = set(explanation.supporting_evidence + explanation.contradicting_evidence)
        references = {key: record for key, record in evidence.items() if record.id in cited}
        if not numbers_grounded(factual_text, references):
            return False
        prose += [explanation.title, explanation.assessment, explanation.uncertainty]
    return all(prose_valid(item) for item in prose)


def apply_narrative(report: Report, value: Narrative, evidence: dict[str, Evidence]) -> Report:
    if not narrative_valid(value, evidence):
        raise ModelFailure("The model assessment failed citation or qualitative-claim validation.")
    explanations = [item.model_dump(mode="json") for item in value.explanations]
    leading = value.explanations[0]
    findings = [item for item in report.findings if item.kind == "observation"]
    findings += [
        Finding(
            kind="hypothesis",
            title=item.title,
            text=item.assessment,
            evidence_ids=list(
                dict.fromkeys(item.supporting_evidence + item.contradicting_evidence)
            ),
        )
        for item in value.explanations
    ]
    confidence = value.confidence
    if report.review_round > 1 or report.hypothesis in {"missing_data", "low_volume"}:
        confidence = "limited"
    return report.model_copy(
        update={
            "headline": leading.title,
            "hypothesis": leading.hypothesis,
            "findings": findings,
            "confidence": confidence,
            "explanations": explanations,
            "analysis_source": "model",
            "limitations": list(
                dict.fromkeys([*report.limitations, *[x.uncertainty for x in value.explanations]])
            ),
            "unresolved_questions": value.unresolved_questions,
            "next_actions": value.next_actions,
        }
    )
