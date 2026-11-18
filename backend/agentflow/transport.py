import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from pydantic import ValidationError

from agentflow.domain import PAYLOADS, Domain, Evidence, Model, RecordRequest

Emit = Callable[[str, str, dict[str, Any]], None]
ALLOWLIST: dict[Domain, frozenset[str]] = {
    "metrics": frozenset(
        {"get_metric_summary", "compare_time_windows", "get_payment_error_breakdown"}
    ),
    "timeline": frozenset({"list_releases", "list_feature_flag_changes"}),
    "support": frozenset({"get_support_category_trends"}),
}
ALL_TOOLS = frozenset(
    {name for names in ALLOWLIST.values() for name in names} | {"get_evidence_record"}
)


class ToolUnavailable(RuntimeError):
    pass


class ToolContractError(RuntimeError):
    pass


@dataclass(frozen=True)
class Call:
    name: str
    request: Model


class MCPClient:
    def __init__(self, url: str) -> None:
        self.url = url

    async def _exchange(
        self, calls: list[Call], node: str, emit: Emit, source: bool = False
    ) -> list[dict[str, Any]]:
        async with (
            asyncio.timeout(8),
            httpx.AsyncClient(timeout=5, trust_env=False, follow_redirects=False) as http,
            streamable_http_client(self.url, http_client=http) as (reader, writer, _),
            ClientSession(reader, writer) as session,
        ):
            await session.initialize()
            if not calls:
                tools = (await session.list_tools()).tools
                if {tool.name for tool in tools} != ALL_TOOLS:
                    raise ToolContractError("MCP tool registry does not match AgentFlow.")
                return []
            results: list[dict[str, Any]] = []
            for call in calls:
                start = perf_counter()
                arguments = call.request.model_dump(mode="json")
                try:
                    result = await session.call_tool(call.name, {"request": arguments})
                    if result.isError or not isinstance(result.structuredContent, dict):
                        raise ToolContractError(f"{call.name} returned an invalid tool result.")
                    content = result.structuredContent
                    if not source:
                        record = Evidence.model_validate(content)
                        PAYLOADS[call.name].model_validate(record.payload)
                        if record.tool != call.name or record.request != arguments:
                            raise ToolContractError(f"{call.name} returned mismatched provenance.")
                except Exception:
                    emit(
                        node,
                        "tool_failed",
                        {
                            "tool": call.name,
                            "request": arguments,
                            "duration_ms": round((perf_counter() - start) * 1000, 1),
                        },
                    )
                    raise
                emit(
                    node,
                    "tool_finished",
                    {
                        "tool": call.name,
                        "request": arguments,
                        "evidence_id": content.get("id"),
                        "duration_ms": round((perf_counter() - start) * 1000, 1),
                    },
                )
                results.append(content)
            return results

    def collect(self, domain: Domain, calls: list[Call], node: str, emit: Emit) -> list[Evidence]:
        if not calls or len(calls) > 5 or any(call.name not in ALLOWLIST[domain] for call in calls):
            emit(node, "tool_denied", {"reason": "outside specialist allowlist"})
            raise ToolContractError("Tool request is outside the specialist's allowlist.")
        for attempt in range(2):
            try:
                return [
                    Evidence.model_validate(row)
                    for row in asyncio.run(self._exchange(calls, node, emit))
                ]
            except Exception as exc:
                invalid, unreachable = exc, exc
                if isinstance(exc, BaseExceptionGroup):
                    # AnyIO wraps errors raised while the transport is open.
                    invalid = exc.subgroup((ToolContractError, ValidationError))  # type: ignore[assignment]
                    unreachable = exc.subgroup((TimeoutError, httpx.TransportError))  # type: ignore[assignment]
                if isinstance(exc, (ToolContractError, ValidationError)) or (
                    isinstance(exc, BaseExceptionGroup) and invalid is not None
                ):
                    raise ToolContractError("MCP returned invalid evidence.") from exc
                retryable = isinstance(exc, (TimeoutError, httpx.TransportError)) or (
                    isinstance(exc, BaseExceptionGroup) and unreachable is not None
                )
                if not retryable or attempt == 1:
                    raise ToolUnavailable(
                        "Northstar MCP is unavailable or the tool timed out."
                    ) from exc
                emit(
                    node,
                    "tool_retry",
                    {"attempt": 2, "reason": "transport timeout or connection error"},
                )
        raise AssertionError("unreachable")

    def ready(self) -> bool:
        try:
            asyncio.run(self._exchange([], "health", discard))
        except Exception:
            return False
        return True

    def source(self, source_id: str) -> dict[str, Any]:
        call = Call("get_evidence_record", RecordRequest(evidence_id=source_id))
        try:
            return asyncio.run(self._exchange([call], "source", discard, source=True))[0]
        except Exception as exc:
            raise ToolUnavailable("The evidence source could not be retrieved.") from exc


def discard(_node: str, _kind: str, _detail: dict[str, Any]) -> None:
    pass
