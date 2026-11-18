from datetime import date, datetime

from agentflow.calculations import compare_traffic, percentage, traffic_totals
from agentflow.domain import (
    PAYLOADS,
    CompareRequest,
    Comparison,
    Evidence,
    Flags,
    MetricRequest,
    Model,
    Payments,
    Plan,
    Releases,
    Scope,
    Tickets,
    TimelineRequest,
    TrafficSummary,
    Window,
)
from agentflow.followups import expected_followups
from agentflow.planning import calls_for


class EvidenceError(RuntimeError):
    pass


def load[T: Model](evidence: dict[str, Evidence], key: str, schema: type[T]) -> T | None:
    record = evidence.get(key)
    return schema.model_validate(record.payload) if record else None


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise EvidenceError(reason)


def _ids(record: Evidence, table: str) -> set[str]:
    ids = {src.id for src in record.sources}
    require(
        len(ids) == len(record.sources) and all(src.table == table for src in record.sources),
        "Source IDs must be unique and match the tool's table.",
    )
    return ids


def _within(day: date, window: Window) -> bool:
    return window.start <= day <= window.end


def _traffic(record: Evidence, req: MetricRequest, data: TrafficSummary) -> None:
    require(
        all(
            _within(row.day, req.window)
            and req.segment in ("all", row.segment)
            and row.purchases <= row.checkout_starts <= row.sessions
            for row in data.rows
        ),
        "Traffic counts or window are inconsistent.",
    )
    ids = _ids(record, "traffic_metrics")
    require(
        len(ids) == len(data.rows)
        and ids == {f"traffic-{row.day}-{row.segment}" for row in data.rows},
        "Traffic rows do not match their source IDs.",
    )
    require(
        data.totals == traffic_totals(data.rows, req), "Traffic denominators failed recomputation."
    )


def _payments(record: Evidence, req: MetricRequest, data: Payments) -> None:
    ids = _ids(record, "payment_events")
    coverage = {(date.fromisoformat(src[4:14]), src.split("-")[4]) for src in ids}
    require(
        all(
            _within(day, req.window)
            and segment in ("web", "mobile")
            and req.segment in ("all", segment)
            for day, segment in coverage
        ),
        "Payment sources fall outside the requested scope.",
    )
    expected = req.window.days * (2 if req.segment == "all" else 1)
    methods = {tuple(src.split("-")[4:]) for src in ids}
    buckets = {(b.segment, b.method, b.outcome) for b in data.buckets}
    require(
        buckets == methods
        and len(buckets) == len(data.buckets)
        and data.total == sum(b.count for b in data.buckets)
        and data.failures == sum(b.count for b in data.buckets if b.outcome != "approved")
        and data.failure_pct == percentage(data.failures, data.total)
        and data.coverage_days == len({day for day, _ in coverage})
        and data.complete == (len(coverage) == expected),
        "Payment totals or coverage failed recomputation.",
    )


def _tickets(record: Evidence, req: TimelineRequest, data: Tickets) -> None:
    ids = _ids(record, "support_tickets")
    dates = {date.fromisoformat(src[7:17]) for src in ids}
    require(
        all(_within(day, req.window) for day in dates)
        and data.days_with_records == len(dates)
        and set(data.excerpts) <= ids
        and len(ids) == data.total
        and data.total == sum(data.categories.values()),
        "Ticket totals or scope are inconsistent.",
    )


def verify(plan: Plan, scope: Scope, evidence: dict[str, Evidence]) -> None:
    expected = {
        key: call for domain in plan.domains for key, call in calls_for(domain, scope).items()
    }
    base_keys = set(expected)
    optional = {
        key: call
        for domain in plan.domains
        for key, call in expected_followups(domain, scope).items()
    }
    selected = {key: call for key, call in optional.items() if key in evidence}
    require(
        all(
            sum(key.startswith("followup_" + domain + "_") for key in selected) <= 1
            for domain in plan.domains
        ),
        "The follow-up budget was exceeded.",
    )
    expected.update(selected)
    require(
        base_keys <= set(evidence) and set(evidence) == set(expected),
        "Evidence is missing or outside the selected plan.",
    )
    for key, call in expected.items():
        record = evidence[key]
        require(
            record.id == record.content_id()
            and record.tool == call.name
            and record.request == call.request.model_dump(mode="json"),
            "Evidence hash or request scope failed verification.",
        )
        payload = PAYLOADS[call.name].model_validate(record.payload)
        if isinstance(payload, TrafficSummary) and isinstance(call.request, MetricRequest):
            _traffic(record, call.request, payload)
        if isinstance(payload, Payments) and isinstance(call.request, MetricRequest):
            _payments(record, call.request, payload)
        if isinstance(payload, Tickets) and isinstance(call.request, TimelineRequest):
            _tickets(record, call.request, payload)
        if isinstance(payload, Releases) and isinstance(call.request, TimelineRequest):
            require(
                _ids(record, "releases") == {r.id for r in payload.records}
                and all(
                    _within(datetime.fromisoformat(r.deployed_at).date(), call.request.window)
                    for r in payload.records
                ),
                "Release source IDs or times are inconsistent.",
            )
        if isinstance(payload, Flags) and isinstance(call.request, TimelineRequest):
            require(
                _ids(record, "feature_flags") == {r.id for r in payload.records}
                and all(
                    _within(datetime.fromisoformat(r.enabled_at).date(), call.request.window)
                    for r in payload.records
                ),
                "Flag source IDs or times are inconsistent.",
            )

    comparison = load(evidence, "comparison", Comparison)
    if comparison:
        before = TrafficSummary.model_validate(evidence["traffic_baseline"].payload)
        after = TrafficSummary.model_validate(evidence["traffic_current"].payload)
        request = CompareRequest.model_validate(evidence["comparison"].request)
        require(
            comparison == compare_traffic(before.rows, after.rows, request),
            "Conversion difference failed independent recomputation from daily rows.",
        )
        require(
            _ids(evidence["comparison"], "traffic_metrics")
            == {
                src.id
                for src in evidence["traffic_baseline"].sources
                + evidence["traffic_current"].sources
            },
            "Comparison sources differ from the supplied traffic rows.",
        )
