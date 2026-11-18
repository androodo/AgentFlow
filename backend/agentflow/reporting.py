import html
import re
from datetime import date, datetime
from typing import Any, Literal

from agentflow.audit import load, require
from agentflow.calculations import percentage
from agentflow.config import DEMO_LABEL
from agentflow.domain import (
    Comparison,
    Decision,
    Evidence,
    Finding,
    Flags,
    Hypothesis,
    Mode,
    Payments,
    Releases,
    Report,
    Scenario,
    Tickets,
    Totals,
    TrafficSummary,
)

EXPLANATIONS: dict[Hypothesis, tuple[str, str, str]] = {
    "missing_data": (
        "Traffic coverage is incomplete",
        "The recorded funnel is too incomplete for a comparable conversion estimate.",
        "Recover missing funnel telemetry before attributing an impact.",
    ),
    "low_volume": (
        "The pilot has a small denominator",
        "A small count of checkouts makes the conversion change sensitive to individual orders.",
        "Collect a longer pilot window with the same segment definitions.",
    ),
    "conflicting_signals": (
        "Support and payment telemetry disagree",
        "Payment complaints rose while recorded payment failures declined.",
        "Check ticket categorization changes and match samples to payment outcomes.",
    ),
    "traffic_drop": (
        "Lower traffic explains most of the order decline",
        "Sessions and purchases moved together while checkout conversion remained stable.",
        "Break down acquisition volume by campaign and confirm the traffic mix.",
    ),
    "stable": (
        "Checkout conversion held steady",
        "The change stays within the investigation's three percentage-point screening threshold.",
        "Monitor the same denominator for another comparable window.",
    ),
    "mix_shift": (
        "Traffic mix best explains the aggregate decline",
        "Each segment held a similar conversion rate as the checkout mix shifted across segments.",
        "Compare like-for-like segment cohorts before attributing the aggregate decline.",
    ),
    "timing_conflict": (
        "The checkout decline precedes the release",
        "At daily resolution, the first affected day comes before the checkout deployment.",
        "Check upstream changes and obtain hourly checkout metrics.",
    ),
    "ambiguous_timeline": (
        "Two checkout releases overlap the decline",
        "Their timing provides multiple plausible explanations for the same change.",
        "Isolate the releases with an exposure cohort or controlled rollback analysis.",
    ),
    "payment_regression": (
        "Payment authentication is the leading hypothesis",
        "Conversion fell alongside concentrated authentication timeouts in the affected window.",
        "Compare payment outcomes by flag exposure and verify with provider logs.",
    ),
    "undetermined": (
        "The conversion change has limited corroboration",
        "The available evidence leaves the cause of the change uncertain.",
        "Fill the payment and support coverage gaps before choosing a cause.",
    ),
    "support_signal": (
        "Support signals point to a customer-facing change",
        "Ticket volume moved around the investigation window and can guide follow-up.",
        "Sample tickets and verify exposure to the associated rollout.",
    ),
    "support_limited": (
        "Support records show limited evidence of change",
        "Recorded category counts provide limited evidence about changes in customer experience.",
        "Check coverage and ticket categorization for both windows.",
    ),
    "timeline_only": (
        "The deployment timeline is available",
        "The selected sources establish timing with limited evidence about business impact.",
        "Compare checkout or support outcomes for the same UTC windows.",
    ),
}
LIMITATION = "The windows show an association. Exposure cohorts or controlled tests are needed to establish causality."


def _checkout_day(summary: TrafficSummary, baseline: Totals) -> date | None:
    for day in sorted({row.day for row in summary.rows}):
        daily = [row for row in summary.rows if row.day == day]
        rate = percentage(
            sum(row.purchases for row in daily), sum(row.checkout_starts for row in daily)
        )
        if (
            rate is not None
            and baseline.conversion_pct is not None
            and rate < baseline.conversion_pct - 3
        ):
            return day
    return None


def _auth_increases(b: Payments, a: Payments) -> list[tuple[int, str, str, int, int]]:
    before = {
        (item.segment, item.method): item.count
        for item in b.buckets
        if item.outcome == "authentication_timeout"
    }
    changes = []
    for item in a.buckets:
        if item.outcome == "authentication_timeout":
            previous = before.get((item.segment, item.method), 0)
            changes.append((item.count - previous, item.segment, item.method, previous, item.count))
    return sorted(changes, reverse=True)


def classify(evidence: dict[str, Evidence]) -> Hypothesis:
    comparison = load(evidence, "comparison", Comparison)
    tb = load(evidence, "tickets_baseline", Tickets)
    ta = load(evidence, "tickets_current", Tickets)
    if comparison is None:
        if tb and ta:
            return "support_signal" if tb.categories != ta.categories else "support_limited"
        return "timeline_only"
    pb = load(evidence, "payments_baseline", Payments)
    pa = load(evidence, "payments_current", Payments)
    releases = load(evidence, "releases", Releases)
    delta = comparison.delta
    before, after = comparison.baseline, comparison.current
    if delta is None:
        return "missing_data"
    if min(before.checkout_starts, after.checkout_starts) < 50:
        return "low_volume"
    if (
        tb
        and ta
        and pb
        and pa
        and pb.complete
        and pa.complete
        and pb.failure_pct is not None
        and pa.failure_pct is not None
        and pa.failure_pct < pb.failure_pct
        and ta.categories.get("payment_failure", 0) - tb.categories.get("payment_failure", 0) >= 3
    ):
        return "conflicting_signals"
    if abs(delta) < 3:
        return "traffic_drop" if after.sessions <= 0.75 * before.sessions else "stable"
    if delta > 0:
        return "undetermined"
    if len(comparison.segments) > 1 and all(
        b.conversion_pct is not None
        and a.conversion_pct is not None
        and abs(a.conversion_pct - b.conversion_pct) < 1
        for b, a in comparison.segments.values()
    ):
        return "mix_shift"
    checkout = [r for r in releases.records if r.area == "checkout"] if releases else []
    daily = load(evidence, "traffic_current", TrafficSummary)
    first_decline = _checkout_day(daily, before) if daily else None
    if (
        first_decline
        and checkout
        and all(datetime.fromisoformat(r.deployed_at).date() > first_decline for r in checkout)
    ):
        return "timing_conflict"
    if len(checkout) > 1:
        return "ambiguous_timeline"
    if (
        pb
        and pa
        and pb.complete
        and pa.complete
        and any(row[0] >= 10 for row in _auth_increases(pb, pa))
    ):
        return "payment_regression"
    return "undetermined"


def _rate(totals: Totals) -> str:
    return f"{totals.conversion_pct:.2f}%" if totals.conversion_pct is not None else "unavailable"


def compose(
    scenario: Scenario,
    mode: Mode,
    model: str | None,
    evidence: dict[str, Evidence],
    round_no: int,
    revision_note: str = "",
) -> Report:
    code = classify(evidence)
    headline, explanation, action = EXPLANATIONS[code]
    findings: list[Finding] = []
    limits = [LIMITATION, "Source records belong to the fictional Northstar Shop dataset."]
    actions = [action]

    def observation(title: str, text: str, *keys: str) -> None:
        findings.append(
            Finding(
                kind="observation",
                title=title,
                text=text,
                evidence_ids=[evidence[key].id for key in keys],
            )
        )

    comparison = load(evidence, "comparison", Comparison)
    if comparison:
        b, a = comparison.baseline, comparison.current
        if comparison.delta is None:
            observation(
                "Funnel coverage",
                f"Traffic was recorded on {b.observed_days} baseline and {a.observed_days} current days. "
                "Conversion requires both comparable windows and nonzero checkout starts.",
                "comparison",
            )
            limits.append("Incomplete traffic coverage makes the conversion change unavailable.")
        else:
            observation(
                "Checkout conversion",
                f"Conversion moved from {_rate(b)} ({b.purchases:,}/{b.checkout_starts:,}) "
                f"to {_rate(a)} ({a.purchases:,}/{a.checkout_starts:,}), "
                f"a change of {comparison.delta:+.2f} percentage points.",
                "comparison",
            )
            observation(
                "Sessions and orders",
                f"Sessions went from {b.sessions:,} to {a.sessions:,}. Completed purchases "
                f"went from {b.purchases:,} to {a.purchases:,}.",
                "traffic_baseline",
                "traffic_current",
            )
            if scenario.scope.segment == "all":
                segments = [
                    f"{segment.title()} {_rate(before)} to {_rate(after)}, with "
                    f"{before.checkout_starts:,} to {after.checkout_starts:,} starts"
                    for segment, (before, after) in sorted(comparison.segments.items())
                ]
                observation("Segment movement", ". ".join(segments) + ".", "comparison")

    pb = load(evidence, "payments_baseline", Payments)
    pa = load(evidence, "payments_current", Payments)
    if (
        pb
        and pa
        and pb.complete
        and pa.complete
        and pb.failure_pct is not None
        and pa.failure_pct is not None
    ):
        observation(
            "Payment failures",
            f"Recorded payment failures went from {pb.failures:,}/{pb.total:,} ({pb.failure_pct:.2f}%) "
            f"to {pa.failures:,}/{pa.total:,} ({pa.failure_pct:.2f}%).",
            "payments_baseline",
            "payments_current",
        )
        changes = _auth_increases(pb, pa)
        if changes and changes[0][0] > 0:
            _, segment, method, b_count, a_count = changes[0]
            observation(
                "Authentication timeouts",
                f"{segment.title()} {method} timeouts went from {b_count:,} to {a_count:,}.",
                "payments_baseline",
                "payments_current",
            )
    elif pb and pa:
        limits.append("Payment coverage is incomplete for the selected segment and dates.")
        observation(
            "Payment coverage",
            f"Payment cohorts were recorded on {pb.coverage_days} baseline and {pa.coverage_days} current days.",
            "payments_baseline",
            "payments_current",
        )

    releases = load(evidence, "releases", Releases)
    flags = load(evidence, "flags", Flags)
    if releases:
        entries = ", ".join(
            f"{r.version} at {r.deployed_at[:16].replace('T', ' ')} UTC" for r in releases.records
        )
        observation(
            "Deployment timeline",
            entries + "." if entries else "The window has no recorded deployments.",
            "releases",
        )
    if flags and flags.records:
        observation(
            "Flag exposure",
            " ".join(
                f"{row.flag} reached {row.rollout_percent}% of the {row.segment} segment."
                for row in flags.records
            ),
            "flags",
        )
    tb = load(evidence, "tickets_baseline", Tickets)
    ta = load(evidence, "tickets_current", Tickets)
    if tb and ta:
        categories = sorted(tb.categories.keys() | ta.categories.keys())
        category_changes = ", ".join(
            f"{c.replace('_', ' ')} {tb.categories.get(c, 0)} to {ta.categories.get(c, 0)}"
            for c in categories
        )
        observation(
            "Support signals",
            f"Recorded tickets went from {tb.total} to {ta.total}."
            + (f" Category counts: {category_changes}." if category_changes else ""),
            "tickets_baseline",
            "tickets_current",
        )
        limits.append(
            "Support records reflect reporting behavior and provide limited coverage of all shoppers."
        )

    findings.append(
        Finding(
            kind="hypothesis",
            title=headline,
            text=explanation,
            evidence_ids=list(
                dict.fromkeys(ev_id for finding in findings for ev_id in finding.evidence_ids)
            ),
        )
    )
    confidence: Literal["limited", "moderate"] = (
        "moderate"
        if code in {"mix_shift", "traffic_drop", "payment_regression", "stable"}
        else "limited"
    )
    if round_no > 1:
        confidence = "limited"
        limits.append(
            "The reviewer asked for a narrower assessment. Confidence is limited pending follow-up."
        )
        if any(word in revision_note.lower() for word in ("timing", "release", "hour")):
            actions.insert(0, "Compare deployment and cohort exposure at hourly resolution.")
        else:
            actions.insert(0, "Independently verify the cited denominator and source coverage.")
    return Report(
        title=scenario.title,
        scenario_id=scenario.id,
        scope=scenario.scope,
        mode=mode,
        mode_label=DEMO_LABEL
        if mode == "demo"
        else {"ollama": "Live local Ollama", "openai": "Live OpenAI", "anthropic": "Live Claude"}[
            mode
        ],
        model=model,
        headline=headline,
        hypothesis=code,
        confidence=confidence,
        findings=findings,
        limitations=limits,
        unresolved_questions=[
            "Which affected and unaffected cohorts can independently validate this assessment?"
        ],
        next_actions=actions,
        comparison=comparison,
        review_round=round_no,
    )


def verify_citations(report: Report, evidence: dict[str, Evidence]) -> None:
    ids = {row.id for row in evidence.values()}
    require(
        bool(report.findings)
        and all(
            bool(item.evidence_ids) and set(item.evidence_ids) <= ids for item in report.findings
        ),
        "The report contains an observation without a verified citation.",
    )


def _escape_markdown(value: str) -> str:
    text = html.escape(" ".join(value.split()), quote=False)
    return re.sub(r"([\\\x60*_{}\[\]()#+.!|])", lambda match: chr(92) + match[0], text)


def markdown(
    run_id: str, report: Report, evidence: list[Evidence], decisions: list[dict[str, Any]]
) -> str:
    b, a = report.scope.baseline, report.scope.current
    lines = [
        f"# {report.title}",
        "",
        report.mode_label,
        "",
        f"**Run:** {run_id}  ",
        f"**Source:** Northstar Shop (synthetic), {report.dataset_version}  ",
        f"**UTC scope:** {b.start} to {b.end} vs. {a.start} to {a.end} ({report.scope.segment})  ",
        f"**Assessment confidence:** {report.confidence}",
        "",
        f"## {report.headline}",
        "",
    ]
    for finding in report.findings:
        refs = " ".join(f"[{ev_id}](#source-{ev_id})" for ev_id in finding.evidence_ids)
        lines += [f"### {finding.kind.title()} · {finding.title}", "", f"{finding.text} {refs}", ""]
    for title, items in (
        ("Limitations", report.limitations),
        ("Unresolved questions", report.unresolved_questions),
        ("Next actions", report.next_actions),
    ):
        lines += [f"## {title}", "", *[f"- {item}" for item in items], ""]
    lines += ["## Evidence", ""]
    for item in sorted(evidence, key=lambda entry: entry.id):
        refs = (
            ", ".join(f"`{src.id}`" for src in item.sources) or "No source records in this window."
        )
        lines += [f'<a id="source-{item.id}"></a>', f"**{item.id}** · {item.tool}", "", refs, ""]
    lines += ["## Review history", ""]
    for row in decisions:
        decision = Decision.model_validate(
            {k: row[k] for k in ("interrupt_id", "round", "action", "note")}
        )
        lines.append(f"- Round {decision.round} · {decision.action} · {row['created_at']}")
        if decision.note:
            lines.append("  - Reviewer note: " + _escape_markdown(decision.note))
    return "\n".join(lines) + "\n"
