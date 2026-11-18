from decimal import Decimal
from typing import Literal

from agentflow.domain import CompareRequest, Comparison, MetricRequest, Totals, TrafficRow


def percentage(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(round(Decimal(100) * numerator / denominator, 4))


def traffic_totals(rows: list[TrafficRow], request: MetricRequest) -> Totals:
    scoped = [row for row in rows if request.segment in ("all", row.segment)]
    starts = sum(row.checkout_starts for row in scoped)
    purchases = sum(row.purchases for row in scoped)
    expected = request.window.days * (2 if request.segment == "all" else 1)
    complete = len({(row.day, row.segment) for row in scoped}) == expected
    return Totals(
        sessions=sum(row.sessions for row in scoped),
        checkout_starts=starts,
        purchases=purchases,
        conversion_pct=percentage(purchases, starts) if complete else None,
        observed_days=len({row.day for row in scoped}),
        complete=complete,
    )


def compare_traffic(
    before: list[TrafficRow], after: list[TrafficRow], request: CompareRequest
) -> Comparison:
    b = traffic_totals(before, MetricRequest(window=request.baseline, segment=request.segment))
    a = traffic_totals(after, MetricRequest(window=request.current, segment=request.segment))
    unit: Literal["percentage_points", "count"] = (
        "percentage_points" if request.metric == "checkout_conversion" else "count"
    )
    delta: float | None = None
    if b.complete and a.complete:
        if unit == "count":
            delta = getattr(a, request.metric) - getattr(b, request.metric)
        elif b.checkout_starts and a.checkout_starts:
            scaled = Decimal(100) * (
                Decimal(a.purchases) / a.checkout_starts - Decimal(b.purchases) / b.checkout_starts
            )
            delta = float(round(scaled, 4))
    segments = {
        segment: (
            traffic_totals(before, MetricRequest(window=request.baseline, segment=segment)),
            traffic_totals(after, MetricRequest(window=request.current, segment=segment)),
        )
        for segment in ("web", "mobile")
        if request.segment in ("all", segment)
    }
    return Comparison(baseline=b, current=a, delta=delta, unit=unit, segments=segments)
