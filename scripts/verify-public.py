"""Exercise the hosted container using independent anonymous browser sessions."""

import argparse
import http.cookiejar
import json
import subprocess
from time import monotonic, sleep
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener


class Visitor:
    def __init__(self, origin: str):
        self.origin = origin.rstrip("/")
        self.cookies = http.cookiejar.CookieJar()
        self.client = build_opener(HTTPCookieProcessor(self.cookies))

    def request(self, path: str, data: dict | None = None, expected: int = 200):
        request = Request(
            self.origin + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "Origin": self.origin}
            if data is not None
            else {},
        )
        try:
            response = self.client.open(request, timeout=12)
        except HTTPError as error:
            assert error.code == expected, (path, error.code, error.read().decode())
            return None
        with response:
            assert response.status == expected
            body = response.read().decode()
            return (
                json.loads(body) if "application/json" in response.headers["Content-Type"] else body
            )


def wait(visitor: Visitor, path: str, status: str):
    deadline = monotonic() + 60
    while monotonic() < deadline:
        row = visitor.request(path)
        if row["status"] == status:
            return row
        assert row["status"] != "failed", row.get("error")
        sleep(0.3)
    raise TimeoutError(path + " did not reach " + status)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:3011")
    parser.add_argument(
        "--restart-local",
        action="store_true",
        help="Restart the local hosted container at its review checkpoint.",
    )
    args = parser.parse_args()
    owner, other = Visitor(args.url), Visitor(args.url)
    assert 'id="root"' in owner.request("/")
    assert owner.request("/api/v1/workspace")["public_demo"]
    assert other.request("/api/v1/investigations") == []
    run = owner.request(
        "/api/v1/investigations", {"scenario_id": "checkout-conversion-drop"}, expected=202
    )
    path = "/api/v1/investigations/" + run["id"]
    pending = wait(owner, path, "awaiting_review")
    assert [item["id"] for item in owner.request("/api/v1/investigations")] == [run["id"]]
    for suffix in ("", "/events", "/evidence", "/report"):
        other.request(path + suffix, expected=404)
    other.request(
        path + "/review",
        {"action": "approve", "interrupt_id": pending["pending"]["interrupt_id"]},
        expected=404,
    )
    if args.restart_local:
        assert args.url.rstrip("/") == "http://127.0.0.1:3011", (
            "Use --restart-local with the default local preview."
        )
        subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "compose.yml",
                "-f",
                "compose.hosted.yml",
                "--profile",
                "hosted",
                "restart",
                "hosted-app",
            ],
            check=True,
        )
        deadline = monotonic() + 60
        while monotonic() < deadline:
            try:
                recovered = owner.request(path)
                break
            except (OSError, AssertionError):
                sleep(0.4)
        else:
            raise TimeoutError("The hosted container did not recover.")
        assert (
            recovered["pending"] == pending["pending"]
            and recovered["checkpoint_id"] == pending["checkpoint_id"]
        )
    owner.request(path + "/report", expected=409)
    decision = {"action": "approve", "interrupt_id": pending["pending"]["interrupt_id"]}
    owner.request(path + "/review", decision, expected=202)
    owner.request(path + "/review", decision, expected=409)
    wait(owner, path, "approved")
    assert "## Evidence" in owner.request(path + "/report?format=markdown")
    for mode in ("ollama", "openai", "anthropic"):
        owner.request(
            "/api/v1/investigations",
            {"scenario_id": "checkout-conversion-drop", "mode": mode},
            expected=403,
        )
    owner.request("/api/v1/evaluations", {}, expected=403)
    owner.request("/api/v1/calibrations", {}, expected=403)
    owner.request("/api/v1/connections/test", {"provider": "openai"}, expected=403)
    owner.request(
        "/api/v1/investigations",
        {"scenario_id": "checkout-conversion-drop", "question": "Custom question about checkout"},
        expected=403,
    )
    for _ in range(10):
        limited = other.request(
            "/api/v1/investigations", {"scenario_id": "healthy-rollout"}, expected=202
        )
        other.request("/api/v1/investigations/" + limited["id"] + "/cancel", {})
    other.request("/api/v1/investigations", {"scenario_id": "healthy-rollout"}, expected=429)
    print(
        "Public workspace checks passed: separate sessions, private review/report, duplicate protection, paid-model restrictions, and per-session rate limits."
    )


if __name__ == "__main__":
    main()
