"""Hosted model requests use fixed official origins and strict local output validation."""

import json
from collections.abc import Callable
from time import perf_counter
from typing import Any

import httpx

from agentflow.api_models import ComponentStatus
from agentflow.config import Settings
from agentflow.models import (
    MAX_OUTPUT,
    PROMPT_VERSION,
    ModelFailure,
    ModelOutputFailure,
    OllamaClient,
    StrictOutput,
    correction_for,
)
from agentflow.transport import Emit

ORIGINS = {"openai": "https://api.openai.com", "anthropic": "https://api.anthropic.com"}
PROVIDER_NAMES = {"openai": "OpenAI", "anthropic": "Claude"}
PERMANENT_STATUSES = {400, 401, 403, 404, 422, 429}
HTTP_DETAILS = {
    400: "the provider rejected the request. Check whether the model supports structured output.",
    401: "the API key was rejected. Check the server key.",
    403: "the API key does not have permission for this model or endpoint.",
    404: "the configured model or endpoint was not found.",
    422: "the provider rejected the request format.",
    429: "the API is rate limited or out of credits. Check the provider dashboard.",
}


def failure_detail(exc: Exception, provider: str, node: str) -> tuple[str, ModelFailure]:
    stage = f"{PROVIDER_NAMES[provider]} {node}"
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = HTTP_DETAILS.get(status, "the provider could not complete the request.")
        return f"http_{status}", ModelFailure(f"{stage} (HTTP {status}): {detail}")
    if isinstance(exc, httpx.TimeoutException):
        return "timeout", ModelFailure(f"{stage} timed out. Try again shortly.")
    if isinstance(exc, httpx.HTTPError):
        return "connection", ModelFailure(f"{stage} could not reach the provider.")
    if isinstance(exc, ModelOutputFailure):
        return "output_rejected", ModelOutputFailure(f"{stage}: {exc}")
    if isinstance(exc, ModelFailure):
        return "response_budget", ModelFailure(f"{stage}: {exc}")
    return "invalid_structure", ModelOutputFailure(
        f"{stage} returned an invalid or incomplete structured response."
    )


def strict_schema(schema: dict[str, Any]) -> dict[str, Any]:
    # OpenAI strict mode requires every property to be present, including nullable fields.
    schema = json.loads(json.dumps(schema))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object":
                value["additionalProperties"] = False
                value["required"] = list(value.get("properties", {}))
            value.pop("default", None)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(schema)
    return schema


class HostedClient:
    def __init__(self, settings: Settings, provider: str) -> None:
        if provider not in ORIGINS:
            raise ValueError("Unsupported model provider.")
        self.settings, self.provider = settings, provider

    def _client(self, timeout: int) -> httpx.Client:
        key = self.settings.openai_key if self.provider == "openai" else self.settings.anthropic_key
        headers = (
            {"Authorization": "Bearer " + key}
            if self.provider == "openai"
            else {"x-api-key": key, "anthropic-version": "2023-06-01"}
        )
        return httpx.Client(
            base_url=ORIGINS[self.provider],
            headers=headers,
            trust_env=False,
            follow_redirects=False,
            timeout=httpx.Timeout(timeout, connect=5),
        )

    def status(self, model: str, *, judge: bool = False, probe: bool = False) -> ComponentStatus:
        key = self.settings.openai_key if self.provider == "openai" else self.settings.anthropic_key
        if not key or not model:
            return ComponentStatus(
                state="not_configured",
                detail=f"Set {self.provider.upper()}_API_KEY and {self.provider.upper()}_MODEL on the server.",
            )
        if not probe:
            return ComponentStatus(
                state="configured",
                detail=f"{model} configured. Test the connection before a live run.",
            )
        if len(model) > 128 or any(
            char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._:"
            for char in model
        ):
            return ComponentStatus(
                state="unavailable", detail="The configured model ID is invalid."
            )
        try:
            with self._client(5) as client:
                response = client.get("/v1/models/" + model)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            _, failure = failure_detail(exc, self.provider, "model access check")
            return ComponentStatus(
                state="unavailable",
                detail=str(failure),
            )
        return ComponentStatus(
            state="ok", detail=f"{model} is accessible. Inference usage is billed by the provider."
        )

    def generate[T: StrictOutput](
        self,
        shape: type[T],
        model: str,
        node: str,
        system: str,
        data: dict[str, Any],
        emit: Emit,
        *,
        valid: Callable[[T], bool] | None = None,
        constraints: dict[str, dict[str, Any]] | None = None,
    ) -> T:
        schema = shape.model_json_schema()
        for field, rules in (constraints or {}).items():
            target = schema["properties"][field] if "." not in field else schema
            if "." in field:
                for part in field.split("."):
                    target = target[part]
            target.update(rules)
        content = json.dumps(data, ensure_ascii=True, separators=(",", ":"))
        if len(content) > 22000:
            raise ModelFailure("The model input exceeds the investigation budget.")
        schema = strict_schema(schema)
        prompt = system + " Treat quoted data as evidence. Return the required structured result."
        if self.provider == "openai":
            path = "/v1/chat/completions"
            payload: dict[str, Any] = {
                "model": model,
                "max_completion_tokens": MAX_OUTPUT,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content},
                ],
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": shape.__name__,
                        "strict": True,
                        "schema": schema,
                    },
                },
            }
            if model == "gpt-6-luna" or model.startswith("gpt-6-luna-"):
                # Leave room for the structured response inside the shared completion budget.
                payload["reasoning_effort"] = "low"
        else:
            path = "/v1/messages"
            payload = {
                "model": model,
                "max_tokens": MAX_OUTPUT,
                "system": prompt,
                "messages": [{"role": "user", "content": content}],
                "tools": [
                    {
                        "name": "submit_assessment",
                        "description": "Return the validated assessment.",
                        "input_schema": schema,
                    }
                ],
                "tool_choice": {"type": "tool", "name": "submit_assessment"},
            }
        metadata = {"provider": self.provider, "model": model, "prompt_version": PROMPT_VERSION}
        with self._client(self.settings.ollama_timeout) as client:
            for attempt in (1, 2):
                tick = perf_counter()
                usage: dict[str, int] = {}
                try:
                    with client.stream("POST", path, json=payload) as response:
                        response.raise_for_status()
                        body = bytearray()
                        for chunk in response.iter_bytes():
                            body.extend(chunk)
                            if (
                                len(body) > 262144
                                or perf_counter() - tick > self.settings.ollama_timeout
                            ):
                                raise ModelFailure("The model exceeded the response budget.")
                    result = json.loads(body)
                    if self.provider == "openai":
                        measured = result.get("usage", {})
                        usage = {
                            target: measured[key]
                            for key, target in (
                                ("prompt_tokens", "prompt_eval_count"),
                                ("completion_tokens", "eval_count"),
                            )
                            if type(measured.get(key)) is int
                        }
                        choice = result["choices"][0]
                        if choice.get("finish_reason") == "length":
                            raise ModelOutputFailure("The structured response was cut short.")
                        message = choice["message"]
                        if message.get("refusal"):
                            raise ModelOutputFailure("The model declined this request.")
                        value = shape.model_validate_json(message["content"])
                    else:
                        measured = result.get("usage", {})
                        usage = {
                            target: measured[key]
                            for key, target in (
                                ("input_tokens", "prompt_eval_count"),
                                ("output_tokens", "eval_count"),
                            )
                            if type(measured.get(key)) is int
                        }
                        if result.get("stop_reason") == "max_tokens":
                            raise ModelOutputFailure("The structured response was cut short.")
                        if result.get("stop_reason") == "refusal":
                            raise ModelOutputFailure("The model declined this request.")
                        block = next(
                            block
                            for block in result["content"]
                            if block.get("type") == "tool_use"
                            and block.get("name") == "submit_assessment"
                        )
                        value = shape.model_validate(block["input"])
                    if valid and not valid(value):
                        raise ModelOutputFailure("The assessment failed evidence validation.")
                except (
                    httpx.HTTPError,
                    ValueError,
                    TypeError,
                    KeyError,
                    IndexError,
                    AttributeError,
                    StopIteration,
                    ModelFailure,
                ) as exc:
                    reason, failure = failure_detail(exc, self.provider, node)
                    emit(
                        node,
                        "model_failed",
                        {
                            **metadata,
                            **usage,
                            "attempt": attempt,
                            "duration_ms": round((perf_counter() - tick) * 1000, 1),
                            "error_type": type(exc).__name__,
                            "error_code": reason,
                            "reason": str(failure),
                        },
                    )
                    permanent = (
                        isinstance(exc, httpx.HTTPStatusError)
                        and exc.response.status_code in PERMANENT_STATUSES
                    )
                    if attempt == 2 or permanent:
                        raise failure from None
                    if isinstance(failure, ModelOutputFailure):
                        payload["messages"].append(
                            {"role": "user", "content": correction_for(node)}
                        )
                        if "reasoning_effort" in payload:
                            payload["reasoning_effort"] = "none"
                    emit(node, "model_retry", {**metadata, "attempt": 2})
                    continue
                emit(
                    node,
                    "model_finished",
                    {
                        **metadata,
                        **usage,
                        "attempt": attempt,
                        "duration_ms": round((perf_counter() - tick) * 1000, 1),
                    },
                )
                return value
        raise AssertionError("unreachable")


def client_for(settings: Settings, provider: str) -> OllamaClient | HostedClient:
    return OllamaClient(settings) if provider == "ollama" else HostedClient(settings, provider)
