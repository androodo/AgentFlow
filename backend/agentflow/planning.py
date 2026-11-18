import re

from agentflow.domain import (
    DOMAINS,
    CompareRequest,
    Domain,
    MetricRequest,
    Plan,
    Scope,
    TimelineRequest,
)
from agentflow.transport import Call

KEYWORDS = {
    "metrics": r"\b(conversion|checkout|payment|payments|wallet|traffic|metric[s]?|sessions|purchases|orders|errors?)\b",
    "timeline": r"\b(releases?|deploy(?:ed|ment|ments)?|roll(?:ed)?out|rollout|flags?|timeline)\b",
    "support": r"\b(support|tickets?|complaints?|contact[s]?)\b",
}
RATIONALES: dict[Domain, str] = {
    "metrics": "Compare the funnel and payment outcomes in both UTC windows.",
    "timeline": "Align deployments and feature flags with the observed change.",
    "support": "Compare ticket categories and record where coverage is sparse.",
}
CLARIFICATION = "Ask about checkout metrics, deployments, or support tickets in the selected case."


def rule_plan(question: str) -> Plan:
    domains = [domain for domain in DOMAINS if re.search(KEYWORDS[domain], question, re.IGNORECASE)]
    return Plan(
        domains=domains,
        rationale=" ".join(RATIONALES[domain] for domain in domains),
        clarification=CLARIFICATION if not domains else None,
    )


def calls_for(domain: Domain, scope: Scope) -> dict[str, Call]:
    before = MetricRequest(window=scope.baseline, segment=scope.segment)
    after = MetricRequest(window=scope.current, segment=scope.segment)
    if domain == "metrics":
        return {
            "traffic_baseline": Call("get_metric_summary", before),
            "traffic_current": Call("get_metric_summary", after),
            "comparison": Call(
                "compare_time_windows",
                CompareRequest(
                    baseline=scope.baseline,
                    current=scope.current,
                    segment=scope.segment,
                ),
            ),
            "payments_baseline": Call("get_payment_error_breakdown", before),
            "payments_current": Call("get_payment_error_breakdown", after),
        }
    if domain == "timeline":
        full = TimelineRequest(window=scope.full)
        return {
            "releases": Call("list_releases", full),
            "flags": Call("list_feature_flag_changes", full),
        }
    return {
        "tickets_baseline": Call(
            "get_support_category_trends", TimelineRequest(window=scope.baseline)
        ),
        "tickets_current": Call(
            "get_support_category_trends", TimelineRequest(window=scope.current)
        ),
    }
