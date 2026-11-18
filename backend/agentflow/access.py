"""Visitor isolation and database-backed resource limits for the public recruiter demo."""

import hashlib
import hmac
import re
import secrets
from uuid import UUID

from sqlalchemy import text
from starlette.requests import Request

from agentflow.config import Settings
from agentflow.store import Problem, Store

COOKIE = "agentflow_visitor"
RUN_ROUTE = re.compile(r"^/api/v1/investigations/([0-9a-fA-F-]{36})(?:/|$)")


def identity(request: Request, settings: Settings) -> tuple[str, str | None]:
    value = request.cookies.get(COOKIE, "")
    visitor, _, signature = value.partition(".")
    expected = hmac.new(
        settings.session_secret.encode(), visitor.encode(), hashlib.sha256
    ).hexdigest()
    if (
        len(visitor) == 32
        and re.fullmatch("[a-f0-9]{32}", visitor)
        and hmac.compare_digest(signature, expected)
    ):
        return visitor, None
    visitor = secrets.token_hex(16)
    signature = hmac.new(
        settings.session_secret.encode(), visitor.encode(), hashlib.sha256
    ).hexdigest()
    return visitor, visitor + "." + signature


def authorize_path(request: Request, store: Store) -> None:
    match = RUN_ROUTE.match(request.url.path)
    if match:
        try:
            run_id = UUID(match[1])
        except ValueError:
            return
        record = store.one("SELECT visitor_id FROM investigations WHERE id=:id", {"id": run_id})
        if not record or record["visitor_id"] != request.state.visitor:
            raise Problem(
                "run_not_found", "This investigation belongs to another browser session.", 404
            )


def reserve_run(store: Store, settings: Settings, visitor: str, address: str) -> None:
    digest = hmac.new(
        settings.session_secret.encode(), address.encode(), hashlib.sha256
    ).hexdigest()
    with store.engine.begin() as connection:
        # Serialize rate reservations; create_run rechecks active capacity under the same lock.
        connection.execute(text("SELECT pg_advisory_xact_lock(189562001)"))
        for key, maximum in (
            ("visitor-" + visitor, 10),
            ("network-" + digest, 30),
            ("global", 300),
        ):
            row = connection.execute(
                text("""INSERT INTO visitor_limits (identity_hash, requests)
                VALUES (:key, 1) ON CONFLICT (identity_hash) DO UPDATE SET
                requests=CASE WHEN visitor_limits.window_start < now()-interval '1 hour'
                              THEN 1 ELSE visitor_limits.requests+1 END,
                window_start=CASE WHEN visitor_limits.window_start < now()-interval '1 hour'
                                  THEN now() ELSE visitor_limits.window_start END
                RETURNING requests"""),
                {"key": key},
            ).scalar_one()
            if row > maximum:
                raise Problem(
                    "demo_limit",
                    "This demo has reached its hourly limit. Please try again later.",
                    429,
                )
        active = connection.execute(
            text("""SELECT count(*) FROM investigations
            WHERE status IN ('queued','running','review_queued','reviewing')""")
        ).scalar_one()
        if active >= 4:
            raise Problem(
                "demo_busy", "Other investigations are running. Try again in a moment.", 429
            )
        # Reservation stays committed while the API creates the queued row.
        recent = connection.execute(
            text("""SELECT count(*) FROM investigations
            WHERE created_at > now()-interval '1 day'""")
        ).scalar_one()
        if recent >= 500:
            raise Problem("demo_daily_limit", "The public demo has reached today's capacity.", 429)


def public_write_allowed(request: Request, settings: Settings) -> None:
    if not settings.public_demo or request.method != "POST":
        return
    path = request.url.path
    allowed = path == "/api/v1/investigations" or bool(
        re.fullmatch(r"/api/v1/investigations/[0-9a-fA-F-]{36}/(review|cancel)", path)
    )
    if not allowed:
        raise Problem(
            "public_demo_readonly",
            "Benchmarks and model settings are managed by the project owner.",
            403,
        )
