import json
from dataclasses import replace

import httpx
import pytest
from agentflow.config import Settings
from agentflow.models import ModelFailure, RouteChoice
from agentflow.providers import HostedClient
from agentflow.transport import discard


@pytest.mark.parametrize("provider", ["openai", "anthropic"])
def test_hosted_request_uses_official_origin_validates_output_and_records_usage(
    provider, monkeypatch
):
    settings = replace(
        Settings.from_env(), openai_key="test-placeholder", anthropic_key="test-placeholder"
    )
    client = HostedClient(settings, provider)
    attempts = []
    events = []

    def upstream(request: httpx.Request):
        assert request.url.host == (
            "api.openai.com" if provider == "openai" else "api.anthropic.com"
        )
        body = json.loads(request.content)
        assert body["model"] == "test-model"
        attempts.append(body)
        value = {"domains": ["unknown"] if len(attempts) == 1 else ["metrics"]}
        if provider == "openai":
            assert request.headers["authorization"] == "Bearer test-placeholder"
            assert body["response_format"]["json_schema"]["strict"]
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": json.dumps(value)}}],
                    "usage": {"prompt_tokens": 40, "completion_tokens": 9},
                },
            )
        assert request.headers["x-api-key"] == "test-placeholder"
        assert body["tool_choice"]["name"] == "submit_assessment"
        return httpx.Response(
            200,
            json={
                "content": [{"type": "tool_use", "name": "submit_assessment", "input": value}],
                "usage": {"input_tokens": 40, "output_tokens": 9},
            },
        )

    original = client._client

    def mock_client(timeout):
        http = original(timeout)
        http.close()
        return httpx.Client(
            base_url=str(http.base_url),
            headers=http.headers,
            transport=httpx.MockTransport(upstream),
        )

    monkeypatch.setattr(client, "_client", mock_client)
    output = client.generate(
        RouteChoice,
        "test-model",
        "planner",
        "Route the request.",
        {},
        lambda node, kind, detail: events.append((kind, detail)),
    )
    assert output.domains == ["metrics"]
    assert len(attempts) == 2
    assert events[-1][1]["eval_count"] == 9
    assert events[-1][1]["provider"] == provider


def test_hosted_auth_failure_has_no_secret_or_provider_body_in_user_error(monkeypatch):
    client = HostedClient(
        replace(Settings.from_env(), openai_key="private-key-placeholder"), "openai"
    )
    requests = []

    def upstream(request):
        requests.append(request)
        return httpx.Response(401, json={"error": {"message": "private-key-placeholder"}})

    monkeypatch.setattr(
        client,
        "_client",
        lambda timeout: httpx.Client(
            base_url="https://api.openai.com", transport=httpx.MockTransport(upstream)
        ),
    )
    with pytest.raises(ModelFailure) as error:
        client.generate(RouteChoice, "test-model", "planner", "Route.", {}, discard)
    assert "private-key" not in str(error.value)
    assert len(requests) == 1


def test_missing_cloud_configuration_is_reported_without_a_network_call():
    client = HostedClient(replace(Settings.from_env(), openai_key="", openai_model=""), "openai")
    assert client.status("").state == "not_configured"
