from collections import Counter
from datetime import UTC, datetime, time, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import text
from sqlalchemy.engine import Engine

from agentflow.calculations import compare_traffic, percentage, traffic_totals
from agentflow.domain import (
    CompareRequest,
    Evidence,
    Flag,
    Flags,
    MetricRequest,
    Model,
    PaymentBucket,
    Payments,
    RecordRequest,
    Release,
    Releases,
    Source,
    Tickets,
    TimelineRequest,
    TrafficRow,
    TrafficSummary,
    Window,
)

ROW_CAP = 256
TABLES = {
    "traffic": "traffic_metrics",
    "pay": "payment_events",
    "ticket": "support_tickets",
    "rel": "releases",
    "flag": "feature_flags",
}


def utc_range(window: Window) -> dict[str, datetime]:
    return {
        "start": datetime.combine(window.start, time.min, UTC),
        "stop": datetime.combine(window.end + timedelta(days=1), time.min, UTC),
    }


def evidence(tool: str, request: Model, sources: list[Source], payload: Model) -> Evidence:
    record = Evidence(
        id="",
        tool=tool,
        request=request.model_dump(mode="json"),
        sources=sorted(sources, key=lambda src: src.id),
        payload=payload.model_dump(mode="json"),
    )
    return record.model_copy(update={"id": record.content_id()})


class OperationsData:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def rows(self, query: str, args: dict[str, Any]) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            result = connection.execute(
                text(query + " LIMIT :row_cap"), {**args, "row_cap": ROW_CAP + 1}
            )
            rows = [dict(row) for row in result.mappings()]
        if len(rows) > ROW_CAP:
            raise ValueError("The request has too many source rows. Use a narrower date range.")
        return rows

    def traffic(self, request: MetricRequest) -> tuple[list[TrafficRow], list[Source]]:
        rows = self.rows(
            """SELECT id, day, segment, sessions, checkout_starts, purchases FROM traffic_metrics
               WHERE day BETWEEN :start AND :end AND (:segment = 'all' OR segment = :segment)
               ORDER BY day, segment""",
            {**request.window.model_dump(), "segment": request.segment},
        )
        sources = [Source(id=row.pop("id"), table="traffic_metrics") for row in rows]
        return [TrafficRow.model_validate(row) for row in rows], sources

    def metrics(self, request: MetricRequest) -> Evidence:
        rows, ids = self.traffic(request)
        return evidence(
            "get_metric_summary",
            request,
            ids,
            TrafficSummary(totals=traffic_totals(rows, request), rows=rows),
        )

    def compare(self, request: CompareRequest) -> Evidence:
        b, b_ids = self.traffic(MetricRequest(window=request.baseline, segment=request.segment))
        a, a_ids = self.traffic(MetricRequest(window=request.current, segment=request.segment))
        return evidence(
            "compare_time_windows", request, b_ids + a_ids, compare_traffic(b, a, request)
        )

    def payments(self, request: MetricRequest) -> Evidence:
        rows = self.rows(
            """SELECT id, observed_at, segment, method, outcome, event_count FROM payment_events
               WHERE observed_at >= :start AND observed_at < :stop
                     AND (:segment = 'all' OR segment = :segment)
               ORDER BY observed_at, id""",
            {**utc_range(request.window), "segment": request.segment},
        )
        counts: Counter[tuple[Any, ...]] = Counter()
        coverage = {(row["observed_at"].date(), row["segment"]) for row in rows}
        for row in rows:
            counts[(row["segment"], row["method"], row["outcome"])] += row["event_count"]
        buckets = [
            PaymentBucket(segment=segment, method=method, outcome=outcome, count=count)
            for (segment, method, outcome), count in sorted(counts.items())
        ]
        total = counts.total()
        failures = sum(row.count for row in buckets if row.outcome != "approved")
        payload = Payments(
            total=total,
            failures=failures,
            failure_pct=percentage(failures, total),
            coverage_days=len({day for day, _ in coverage}),
            complete=len(coverage) == request.window.days * (2 if request.segment == "all" else 1),
            buckets=buckets,
        )
        return evidence(
            "get_payment_error_breakdown",
            request,
            [Source(id=row["id"], table="payment_events") for row in rows],
            payload,
        )

    def releases(self, request: TimelineRequest) -> Evidence:
        rows = self.rows(
            """SELECT id, version, deployed_at, area, description FROM releases
               WHERE deployed_at >= :start AND deployed_at < :stop ORDER BY deployed_at, id""",
            utc_range(request.window),
        )
        payload = Releases(records=[Release.model_validate(jsonable_encoder(row)) for row in rows])
        return evidence(
            "list_releases",
            request,
            [Source(id=row["id"], table="releases") for row in rows],
            payload,
        )

    def flags(self, request: TimelineRequest) -> Evidence:
        rows = self.rows(
            """SELECT id, release_id, flag, segment, enabled_at, rollout_percent FROM feature_flags
               WHERE enabled_at >= :start AND enabled_at < :stop ORDER BY enabled_at, id""",
            utc_range(request.window),
        )
        payload = Flags(records=[Flag.model_validate(jsonable_encoder(row)) for row in rows])
        return evidence(
            "list_feature_flag_changes",
            request,
            [Source(id=row["id"], table="feature_flags") for row in rows],
            payload,
        )

    def tickets(self, request: TimelineRequest) -> Evidence:
        rows = self.rows(
            """SELECT id, created_at, category, severity, excerpt FROM support_tickets
               WHERE created_at >= :start AND created_at < :stop ORDER BY created_at, id""",
            utc_range(request.window),
        )
        payload = Tickets(
            total=len(rows),
            categories=dict(Counter(row["category"] for row in rows)),
            days_with_records=len({row["created_at"].date() for row in rows}),
            excerpts={row["id"]: row["excerpt"] for row in rows[:8]},
        )
        return evidence(
            "get_support_category_trends",
            request,
            [Source(id=row["id"], table="support_tickets") for row in rows],
            payload,
        )

    def source(self, request: RecordRequest) -> dict[str, Any]:
        table = TABLES[request.evidence_id.partition("-")[0]]
        # Table comes exclusively from the constant registry. The ID is always bound.
        rows = self.rows(f"SELECT * FROM {table} WHERE id = :id", {"id": request.evidence_id})
        if not rows:
            raise ValueError("Source record does not exist.")
        return {"table": table, "record": jsonable_encoder(rows[0])}
