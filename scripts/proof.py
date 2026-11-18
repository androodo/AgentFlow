"""Compare two seeds and exercise checkpoint recovery through the published local API."""

import hashlib
import json
import subprocess
from time import monotonic, sleep
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

TABLES = ("releases", "feature_flags", "traffic_metrics", "payment_events", "support_tickets")


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], check=True)


def output(*args: str) -> str:
    return subprocess.check_output(["docker", "compose", *args], text=True).strip()


def fingerprint() -> str:
    snapshots = []
    for table in TABLES:
        query = f"SELECT row_to_json(source)::text FROM {table} AS source ORDER BY id"
        snapshots.append(
            output(
                "exec",
                "-T",
                "db",
                "psql",
                "-XAt",
                "-U",
                "agentflow_admin",
                "-d",
                "agentflow",
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                query,
            )
        )
    return hashlib.sha256("\n".join(snapshots).encode("utf-8")).hexdigest()


def request(url: str, path: str, payload: dict | None = None, expected: int = 200):
    data = json.dumps(payload).encode() if payload is not None else None
    req = Request(
        url + path, data, {"Content-Type": "application/json"} if data is not None else {}
    )
    try:
        with urlopen(req, timeout=10) as response:
            assert response.status == expected, (path, response.status, expected)
            raw = response.read().decode()
            return json.loads(raw) if "json" in response.headers["Content-Type"] else raw
    except HTTPError as error:
        if error.code != expected:
            raise
        return json.loads(error.read())


def wait(url: str, path: str, status: str, expected: int = 200):
    deadline = monotonic() + 45
    while monotonic() < deadline:
        try:
            row = request(url, path, expected=expected)
            current = row.get("status", row.get("mcp"))
            if current == status:
                return row
            if current in {"failed", "rejected", "needs_clarification"}:
                raise AssertionError(row.get("error", current))
        except (URLError, ConnectionError, TimeoutError):
            pass
        sleep(0.3)
    raise TimeoutError(f"{path} did not reach {status}")


def main() -> None:
    first = fingerprint()
    for _ in range(2):
        compose("run", "--rm", "--no-deps", "bootstrap")
        assert fingerprint() == first
    print(f"Source dataset identical after two bootstrap runs: sha256:{first}")

    api = "http://" + output("port", "api", "8001")
    start = request(
        api, "/api/v1/investigations", {"scenario_id": "checkout-conversion-drop"}, expected=202
    )
    path = "/api/v1/investigations/" + start["id"]
    before = wait(api, path, "awaiting_review")
    assert (
        request(api, path + "/report", expected=409)["error"]["code"] == "report_pending_approval"
    )
    events = request(api, path + "/events")["events"]
    assert any(event["kind"] == "tool_finished" for event in events)
    assert any(event["kind"] == "evidence_verified" for event in events)
    compose("restart", "api")
    wait(api, "/readyz", "ok")
    after = wait(api, path, "awaiting_review")
    assert (
        after["checkpoint_id"] == before["checkpoint_id"] and after["pending"] == before["pending"]
    )
    decision = {
        "interrupt_id": after["pending"]["interrupt_id"],
        "action": "approve",
        "note": "Restart proof",
    }
    request(api, path + "/review", decision, expected=202)
    assert (
        request(api, path + "/review", decision, expected=409)["error"]["code"] == "review_conflict"
    )
    result = wait(api, path, "approved")
    assert len(result["reviews"]) == 1
    markdown = request(api, path + "/report?format=markdown")
    assert "## Evidence" in markdown and "traffic-2025-10-21-mobile" in markdown
    print(
        "API restart retained the interrupt. Exactly one decision produced the cited Markdown export."
    )

    try:
        compose("stop", "mcp")
        assert request(api, "/healthz")["api"] == "ok"
        unavailable = wait(api, "/readyz", "unavailable", expected=503)
        assert unavailable["database"] == "ok"
        outage = request(
            api, "/api/v1/investigations", {"scenario_id": "traffic-shift"}, expected=202
        )
        outage_path = "/api/v1/investigations/" + outage["id"]
        failed = wait(api, outage_path, "failed")
        assert "MCP" in failed["error"]
        events = request(api, outage_path + "/events")["events"]
        assert any(row["kind"] == "tool_retry" for row in events)
        print(
            "MCP outage was visible in readiness and the investigation failed after a bounded retry."
        )
    finally:
        compose("up", "-d", "--wait", "--wait-timeout", "90", "mcp")
    wait(api, "/readyz", "ok")
    print("MCP and API readiness recovered.")


if __name__ == "__main__":
    main()
