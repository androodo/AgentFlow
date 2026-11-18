import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from agentflow.domain import Decision, Evidence, Mode, Scenario

Row = dict[str, Any]


@dataclass
class Problem(Exception):
    code: str
    message: str
    status: int = 400


def _params(values: Row | None) -> Row:
    return values if values is not None else {}


def _one(connection: Connection, query: str, values: Row | None = None) -> Row | None:
    row = connection.execute(text(query), _params(values)).mappings().first()
    return dict(row) if row is not None else None


def _all(connection: Connection, query: str, values: Row | None = None) -> list[Row]:
    return [dict(row) for row in connection.execute(text(query), _params(values)).mappings()]


def encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class Store:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def one(self, query: str, values: Row | None = None) -> Row | None:
        with self.engine.connect() as connection:
            return _one(connection, query, values)

    def all(self, query: str, values: Row | None = None) -> list[Row]:
        with self.engine.connect() as connection:
            return _all(connection, query, values)

    @staticmethod
    def _run(connection: Connection, run_id: UUID, *, lock: bool = False) -> Row:
        row = _one(
            connection,
            "SELECT * FROM investigations WHERE id = :id" + (" FOR UPDATE" if lock else ""),
            {"id": run_id},
        )
        if row is None:
            raise Problem("run_not_found", "Investigation could not be found.", 404)
        return row

    @staticmethod
    def _event(connection: Connection, run_id: UUID, node: str, kind: str, detail: Row) -> None:
        connection.execute(
            text(
                "INSERT INTO trace_events (run_id, node, kind, detail) VALUES (:id,:node,:kind,CAST(:detail AS jsonb))"
            ),
            {"id": run_id, "node": node, "kind": kind, "detail": encode(detail)},
        )

    def event(self, run_id: UUID, node: str, kind: str, detail: Row) -> None:
        with self.engine.begin() as connection:
            # Serialize each run's event commits so an ID cursor cannot skip an in-flight event.
            row = self._run(connection, run_id, lock=True)
            if row["status"] == "canceled":
                raise Problem("canceled", "The investigation was canceled.", 409)
            self._event(connection, run_id, node, kind, detail)

    def create_run(
        self,
        scenario: Scenario,
        question: str,
        mode: Mode,
        model: str | None,
        visitor_id: str | None = None,
    ) -> Row:
        run_id = uuid4()
        with self.engine.begin() as connection:
            if visitor_id:
                # Recheck capacity at insertion: reserve_run committed in an earlier transaction.
                connection.execute(text("SELECT pg_advisory_xact_lock(189562001)"))
                active = connection.execute(
                    text("""SELECT count(*) FROM investigations
                    WHERE status IN ('queued','running','review_queued','reviewing')""")
                ).scalar_one()
                if active >= 4:
                    raise Problem(
                        "demo_busy", "Other investigations are running. Try again shortly.", 429
                    )
            connection.execute(
                text(
                    """INSERT INTO investigations (id, scenario, question, mode, model, status, visitor_id)
                   VALUES (:id,CAST(:scenario AS jsonb),:question,:mode,:model,'queued',:visitor)"""
                ),
                {
                    "id": run_id,
                    "scenario": scenario.model_dump_json(),
                    "question": question,
                    "mode": mode,
                    "model": model,
                    "visitor": visitor_id,
                },
            )
            self._event(connection, run_id, "workflow", "queued", {"mode": mode, "model": model})
            return self._run(connection, run_id)

    def get_run(self, run_id: UUID) -> Row:
        with self.engine.connect() as connection:
            row = self._run(connection, run_id)
            row["reviews"] = _all(
                connection,
                """SELECT round, interrupt_id, action, note, created_at FROM review_decisions
                   WHERE run_id = :id ORDER BY round""",
                {"id": run_id},
            )
            return row

    def events(self, run_id: UUID, cursor: int) -> list[Row]:
        with self.engine.connect() as connection:
            self._run(connection, run_id)
            return _all(
                connection,
                """SELECT id, node, kind, detail, occurred_at FROM trace_events
                   WHERE run_id = :id AND id > :cursor ORDER BY id LIMIT 200""",
                {"id": run_id, "cursor": cursor},
            )

    def queue_review(self, run_id: UUID, interrupt_id: str, action: str, note: str) -> None:
        with self.engine.begin() as connection:
            row = self._run(connection, run_id, lock=True)
            # Lock the row and persist the decision before the worker resumes the graph.
            # The unique ledger key also rejects a duplicate decision after a retry.
            pending = row["pending"]
            if (
                row["status"] != "awaiting_review"
                or not pending
                or pending["interrupt_id"] != interrupt_id
            ):
                raise Problem(
                    "review_conflict", "This checkpoint is no longer accepting a review.", 409
                )
            round_no = pending["round"]
            if action == "revise" and round_no >= 2:
                raise Problem("revision_limit", "This investigation has used its revision.", 409)
            connection.execute(
                text(
                    """INSERT INTO review_decisions (run_id, round, interrupt_id, action, note)
                   VALUES (:id,:round,:interrupt_id,:action,:note)"""
                ),
                {
                    "id": run_id,
                    "round": round_no,
                    "interrupt_id": interrupt_id,
                    "action": action,
                    "note": note,
                },
            )
            connection.execute(
                text(
                    "UPDATE investigations SET status='review_queued',updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"id": run_id},
            )
            self._event(
                connection,
                run_id,
                "review",
                "decision_recorded",
                {"round": round_no, "action": action, "interrupt_id": interrupt_id},
            )

    def cancel(self, run_id: UUID) -> None:
        with self.engine.begin() as connection:
            row = self._run(connection, run_id, lock=True)
            if row["status"] not in {"queued", "running", "awaiting_review"}:
                raise Problem(
                    "cancel_conflict",
                    "The investigation cannot be canceled from its current state.",
                    409,
                )
            connection.execute(
                text(
                    """UPDATE investigations SET status='canceled',pending=NULL,updated_at=clock_timestamp()
                   WHERE id=:id"""
                ),
                {"id": run_id},
            )
            self._event(connection, run_id, "workflow", "canceled", {})

    def claim(self) -> Row | None:
        with self.engine.begin() as connection:
            row = _one(
                connection,
                """SELECT * FROM investigations
                WHERE status IN ('queued','running','review_queued','reviewing')
                ORDER BY updated_at, created_at LIMIT 1 FOR UPDATE""",
            )
            if row is None:
                return None
            status = row["status"]
            active = "reviewing" if status in {"review_queued", "reviewing"} else "running"
            connection.execute(
                text(
                    "UPDATE investigations SET status=:status,updated_at=clock_timestamp() WHERE id=:id"
                ),
                {"status": active, "id": row["id"]},
            )
            self._event(
                connection,
                row["id"],
                "workflow",
                "worker_recovered" if status == active else "worker_started",
                {"mode": row["mode"], "model": row["model"], "status": active},
            )
            row["status"] = active
            return row

    def synchronize(
        self,
        run_id: UUID,
        status: str,
        checkpoint: str | None,
        evidence: Sequence[Evidence],
        draft: Row | None,
        pending: Row | None,
        decision: Decision | None,
        error: str | None = None,
    ) -> None:
        with self.engine.begin() as connection:
            row = self._run(connection, run_id, lock=True)
            if row["status"] == "canceled":
                return
            for record in evidence:
                connection.execute(
                    text(
                        """INSERT INTO evidence (run_id,id,record) VALUES (:id,:ev,CAST(:record AS jsonb))
                       ON CONFLICT (run_id,id) DO NOTHING"""
                    ),
                    {"id": run_id, "ev": record.id, "record": record.model_dump_json()},
                )
            if status == "approved":
                # Checkpoint replay may reach here again; export once, only with a durable approval.
                if not draft or not decision or decision.action != "approve":
                    raise RuntimeError("An approved graph requires a draft and approval.")
                authorized = _one(
                    connection,
                    """SELECT 1 FROM review_decisions WHERE
                    run_id=:id AND round=:round AND interrupt_id=:interrupt AND action='approve'""",
                    {"id": run_id, "round": decision.round, "interrupt": decision.interrupt_id},
                )
                if not authorized:
                    raise RuntimeError("Approval is missing from the review ledger.")
                connection.execute(
                    text(
                        """INSERT INTO reports (run_id,approved_round,report) VALUES (:id,:round,CAST(:report AS jsonb))
                       ON CONFLICT (run_id) DO NOTHING"""
                    ),
                    {"id": run_id, "round": decision.round, "report": encode(draft)},
                )
            connection.execute(
                text(
                    """UPDATE investigations SET status=:status,checkpoint_id=:checkpoint,
                   draft=CAST(:draft AS jsonb), pending=CAST(:pending AS jsonb), error=:error,
                   updated_at=clock_timestamp() WHERE id=:id"""
                ),
                {
                    "id": run_id,
                    "status": status,
                    "checkpoint": checkpoint,
                    "draft": encode(draft) if draft is not None else None,
                    "pending": encode(pending) if pending is not None else None,
                    "error": error,
                },
            )
            self._event(
                connection,
                run_id,
                "review" if pending or decision else "workflow",
                status,
                {"checkpoint_id": checkpoint, "pending": pending},
            )

    def fail(self, run_id: UUID, message: str) -> None:
        with self.engine.begin() as connection:
            row = self._run(connection, run_id, lock=True)
            if row["status"] == "canceled":
                return
            connection.execute(
                text(
                    """UPDATE investigations SET status='failed',error=:error,pending=NULL,
                   updated_at=clock_timestamp() WHERE id=:id"""
                ),
                {"id": run_id, "error": message},
            )
            self._event(connection, run_id, "workflow", "failed", {"error": message})
