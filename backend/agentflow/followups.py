"""Code-owned follow-up recipes. A model selects a label within its domain."""

from typing import Literal

from agentflow.domain import Domain, MetricRequest, Scope, Segment, TimelineRequest
from agentflow.transport import Call

FollowUp = Literal["none", "mobile_payments", "web_payments", "release_day", "tickets_release_day"]
OPTIONS: dict[Domain, dict[str, str]] = {
    "metrics": {
        "mobile_payments": "Inspect mobile payment outcomes in the current window.",
        "web_payments": "Inspect web payment outcomes in the current window.",
    },
    "timeline": {"release_day": "Check releases on the first day of the current window."},
    "support": {
        "tickets_release_day": "Check ticket categories on the first day of the current window."
    },
}


def followup_call(domain: Domain, selection: str, scope: Scope) -> tuple[str, Call]:
    if selection not in OPTIONS[domain]:
        raise ValueError("The follow-up is outside this specialist's recipes.")
    if selection in {"mobile_payments", "web_payments"}:
        segment: Segment = "mobile" if selection == "mobile_payments" else "web"
        if scope.segment not in ("all", segment):
            raise ValueError("The follow-up is outside the selected segment.")
        request = MetricRequest(window=scope.current, segment=segment)
        call = Call("get_payment_error_breakdown", request)
    else:
        window = scope.current.model_copy(update={"end": scope.current.start})
        call = Call(
            "list_releases" if domain == "timeline" else "get_support_category_trends",
            TimelineRequest(window=window),
        )
    return "followup_" + domain + "_" + selection, call


def options_for(domain: Domain, scope: Scope) -> dict[str, str]:
    options = dict(OPTIONS[domain])
    if domain == "metrics" and scope.segment != "all":
        options.pop("web_payments" if scope.segment == "mobile" else "mobile_payments")
    return options


def expected_followups(domain: Domain, scope: Scope) -> dict[str, Call]:
    return {
        key: call
        for choice in options_for(domain, scope)
        for key, call in [followup_call(domain, choice, scope)]
    }
