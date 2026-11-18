"""Single Render web container, with a separate loopback-only MCP process."""

import os
import signal
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener

from agentflow.config import db_fields
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def wait_for_mcp(process: subprocess.Popen, timeout: float = 75) -> None:
    # A cold import can take longer on Render's free CPU. Probe loopback directly.
    opener = build_opener(ProxyHandler({}))
    deadline = time.monotonic() + timeout
    last_probe = "no response"
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"MCP exited during startup (return code {exit_code}).")
        try:
            with opener.open("http://127.0.0.1:8002/healthz", timeout=2) as response:
                if response.status == 200:
                    return
                last_probe = f"HTTP {response.status}"
        except HTTPError as exc:
            last_probe = f"HTTP {exc.code}"
            exc.close()
        except OSError as exc:
            last_probe = type(exc).__name__
        time.sleep(0.5)
    raise RuntimeError(f"MCP did not become ready within {timeout:g}s (last probe: {last_probe}).")


def role_url(admin: str, role: str, password: str) -> str:
    fields = conninfo_to_dict(admin)
    if "-pooler." in fields.get("host", ""):
        raise ValueError("Use a direct PostgreSQL endpoint so session advisory locks remain valid.")
    fields.update(user=role, password=password)
    return make_conninfo("", **fields)


def main() -> None:
    admin = os.environ.get("ADMIN_DATABASE_URL", "")
    if not admin and os.environ.get("DB_HOST"):
        admin = make_conninfo("", **db_fields())
    if not admin:
        raise RuntimeError("Configure ADMIN_DATABASE_URL in the Render secret settings.")
    subprocess.run(
        [sys.executable, "-m", "agentflow.bootstrap"],
        env={**os.environ, "DATABASE_URL": admin},
        check=True,
    )
    app_url = role_url(admin, "agentflow_app", os.environ["APP_DB_PASSWORD"])
    reader_url = role_url(admin, "agentflow_reader", os.environ["READER_DB_PASSWORD"])
    # Bootstrap needs the owner role; long-lived services get only their restricted DSNs.
    runtime = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "ADMIN_DATABASE_URL",
            "APP_DB_PASSWORD",
            "READER_DB_PASSWORD",
            "DB_USER",
            "DB_PASSWORD",
        }
    }
    if not runtime.get("AGENTFLOW_PUBLIC_ORIGIN") and runtime.get("RENDER_EXTERNAL_URL"):
        runtime["AGENTFLOW_PUBLIC_ORIGIN"] = runtime["RENDER_EXTERNAL_URL"]
    mcp_env = {
        key: value
        for key, value in runtime.items()
        if key
        not in {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "LANGSMITH_API_KEY",
            "AGENTFLOW_SESSION_SECRET",
        }
    }
    processes: list[subprocess.Popen] = []

    def shutdown(_signum=None, _frame=None) -> None:
        for process in processes:
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    try:
        print("Starting the MCP service on loopback.", flush=True)
        mcp = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "server:app",
                "--app-dir",
                "mcp-server",
                "--host",
                "127.0.0.1",
                "--port",
                "8002",
                "--no-access-log",
            ],
            env={**mcp_env, "DATABASE_URL": reader_url},
        )
        processes.append(mcp)
        wait_for_mcp(mcp)
        print("MCP is ready. Starting the web service.", flush=True)
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "agentflow.api:app",
                "--host",
                "0.0.0.0",
                "--port",
                os.environ.get("PORT", "10000"),
                "--workers",
                "1",
                "--timeout-graceful-shutdown",
                "5",
                "--proxy-headers",
                "--forwarded-allow-ips",
                "*",
            ],
            env={**runtime, "DATABASE_URL": app_url},
        )
        processes.append(api)
        while all(process.poll() is None for process in processes):
            time.sleep(0.5)
        raise SystemExit(next((p.returncode for p in processes if p.poll() is not None), 1))
    finally:
        shutdown()
        for process in processes:
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    main()
