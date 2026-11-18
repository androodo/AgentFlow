from dataclasses import dataclass
from os import environ
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict, make_conninfo
from sqlalchemy import URL, create_engine
from sqlalchemy.engine import Engine

ROOT = Path(__file__).resolve().parents[2]
DEMO_LABEL = "Rule-based demo — no LLM involved"
DATASET_VERSION = "northstar-2"


def db_fields() -> dict[str, Any]:
    if environ.get("DATABASE_URL"):
        return conninfo_to_dict(environ["DATABASE_URL"])
    return {
        "host": environ.get("DB_HOST", "127.0.0.1"),
        "port": int(environ.get("DB_PORT", "5432")),
        "dbname": environ.get("DB_NAME", "agentflow"),
        "user": environ.get("DB_USER", "agentflow_app"),
        "password": environ.get("DB_PASSWORD", "northstar-local-app"),
    }


def conninfo(*, checkpoints: bool = False) -> str:
    options = "-c search_path=checkpoints -c statement_timeout=15000" if checkpoints else ""
    return make_conninfo("", **db_fields(), options=options, connect_timeout=4)


def make_engine(*, read_only: bool = False) -> Engine:
    fields = db_fields()
    url = URL.create("postgresql+psycopg")
    options = "-c timezone=UTC -c statement_timeout=5000"
    if read_only:
        options += " -c default_transaction_read_only=on"
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=3,
        max_overflow=3,
        connect_args={**fields, "connect_timeout": 8, "options": options},
    )


def _local_url(value: str, hosts: set[str], path: str) -> str:
    url = urlsplit(value)
    if (
        url.scheme != "http"
        or url.hostname not in hosts
        or url.username
        or url.password
        or url.path.rstrip("/") != path
        or url.query
        or url.fragment
        or not url.port
    ):
        raise ValueError("Use the documented, allowlisted local service URL with an explicit port.")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    mcp_url: str
    ollama_url: str
    ollama_model: str
    judge_model: str
    ollama_timeout: int
    langsmith_enabled: bool
    langsmith_key: str
    langsmith_project: str
    embedded_worker: bool
    openai_key: str = ""
    openai_model: str = ""
    anthropic_key: str = ""
    anthropic_model: str = ""
    public_demo: bool = False
    public_live_daily_limit: int = 0
    session_secret: str = ""
    public_origin: str = ""

    def model_for(self, provider: str) -> str:
        return {
            "ollama": self.ollama_model,
            "openai": self.openai_model,
            "anthropic": self.anthropic_model,
        }.get(provider, "")

    @classmethod
    def from_env(cls) -> "Settings":
        public = environ.get("AGENTFLOW_PUBLIC_DEMO") == "true"
        origin = environ.get("AGENTFLOW_PUBLIC_ORIGIN", "").rstrip("/")
        secret = environ.get("AGENTFLOW_SESSION_SECRET", "")
        if public and len(secret) < 32:
            raise ValueError("Public demo requires a session secret with at least 32 characters.")
        if origin and (
            urlsplit(origin).scheme not in {"https", "http"}
            or not urlsplit(origin).netloc
            or urlsplit(origin).path
            or urlsplit(origin).query
            or urlsplit(origin).fragment
        ):
            raise ValueError("Set a single public origin with scheme and host.")
        return cls(
            mcp_url=_local_url(
                environ.get("MCP_URL", "http://127.0.0.1:8002/mcp"),
                {"localhost", "127.0.0.1", "mcp"},
                "/mcp",
            ),
            ollama_url=_local_url(
                environ.get("OLLAMA_URL", "http://127.0.0.1:11434"),
                {"localhost", "127.0.0.1", "host.docker.internal"},
                "",
            ),
            ollama_model=environ.get("OLLAMA_MODEL", "").strip(),
            judge_model=environ.get("OLLAMA_JUDGE_MODEL", "").strip(),
            ollama_timeout=max(5, min(90, int(environ.get("OLLAMA_TIMEOUT_SECONDS", "45")))),
            langsmith_enabled=environ.get("AGENTFLOW_LANGSMITH") == "true",
            langsmith_key=environ.get("LANGSMITH_API_KEY", ""),
            langsmith_project=environ.get("LANGSMITH_PROJECT", "agentflow"),
            embedded_worker=environ.get("AGENTFLOW_EMBEDDED_WORKER", "true") == "true",
            openai_key=environ.get("OPENAI_API_KEY", ""),
            openai_model=environ.get("OPENAI_MODEL", ""),
            anthropic_key=environ.get("ANTHROPIC_API_KEY", ""),
            anthropic_model=environ.get("ANTHROPIC_MODEL", ""),
            public_demo=public,
            public_live_daily_limit=max(
                0, min(20, int(environ.get("AGENTFLOW_PUBLIC_LIVE_DAILY_LIMIT", "0")))
            ),
            session_secret=secret,
            public_origin=origin,
        )
