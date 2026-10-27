# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One transactional fact store, with SQLite and PostgreSQL dialects."""

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    create_engine,
    event,
    text,
)
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from datakeel.core.models import new_id, utcnow
from datakeel.core.settings import get_settings
from datakeel.storage.action_rows import (
    ActionAuditRow,
    ActionOperationRow,
    ActionPlanRow,
    ActionRunRow,
    ApprovalRow,
)
from datakeel.storage.ask_rows import AskAnswerRow, AskSessionRow
from datakeel.storage.base import Base
from datakeel.storage.budget_rows import BudgetAccountRow, BudgetReservationRow
from datakeel.storage.catalog_rows import CatalogEdgeRow, CatalogObjectRow
from datakeel.storage.checkpoint_store import CheckpointRow, CheckpointWriteRow
from datakeel.storage.conversation_rows import (
    ConversationAuditRow,
    ConversationRequestRow,
    ConversationResumeRow,
    ConversationRow,
)
from datakeel.storage.datasheet_job_rows import DatasheetJobRow
from datakeel.storage.datasheet_rows import DatasheetRow
from datakeel.storage.evidence_constraints import install_evidence_constraints
from datakeel.storage.evidence_rows import AssertionDecisionRow, AssertionRow, EvidenceCacheRow
from datakeel.storage.file_state import FileStateRow
from datakeel.storage.harness_rows import EvalRunRow, ModelCallTraceRow
from datakeel.storage.kg_eval_rows import KGEvalRunRow
from datakeel.storage.kg_rows import KGCacheRow, KGRunRow
from datakeel.storage.memory_rows import MemoryAuditRow, MemoryRow, MemoryUseRow, MemoryWriteRow
from datakeel.storage.metric_audit import MetricAuditRow
from datakeel.storage.migrations import add_nullable_columns
from datakeel.storage.tool_rows import ToolInvocationRow
from datakeel.storage.transcription_rows import TranscriptionRow
from datakeel.storage.workflow_rows import (
    WorkflowAuditRow,
    WorkflowResumeRow,
    WorkflowRunRow,
    WorkflowStepRow,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

# Loading each mapping registers it in the single migration metadata collection.
_REGISTERED_MODELS = (
    ActionAuditRow,
    ActionOperationRow,
    ActionPlanRow,
    ActionRunRow,
    ApprovalRow,
    FileStateRow,
    DatasheetJobRow,
    BudgetAccountRow,
    BudgetReservationRow,
    ConversationRequestRow,
    ConversationRow,
    ConversationResumeRow,
    ConversationAuditRow,
    EvalRunRow,
    KGEvalRunRow,
    KGCacheRow,
    KGRunRow,
    ModelCallTraceRow,
    MemoryRow,
    MemoryWriteRow,
    MemoryUseRow,
    MemoryAuditRow,
    ToolInvocationRow,
    TranscriptionRow,
    AssertionRow,
    AssertionDecisionRow,
    EvidenceCacheRow,
    CatalogObjectRow,
    CatalogEdgeRow,
    MetricAuditRow,
    AskSessionRow,
    AskAnswerRow,
    DatasheetRow,
    CheckpointRow,
    CheckpointWriteRow,
    WorkflowRunRow,
    WorkflowStepRow,
    WorkflowAuditRow,
    WorkflowResumeRow,
)


def data_dir() -> Path:
    """Resolve and initialize the configured local data directory."""
    path = get_settings().home.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


class DatasetRow(Base):
    """Internal persistence record for dataset facts."""

    __tablename__ = "datasets"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    files: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    quality_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    template: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    metadata_values: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    compliance: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class VersionRow(Base):
    """Internal persistence record for version facts."""

    __tablename__ = "versions"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    manifest: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    task_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)


class EventRow(Base):
    """Internal persistence record for event facts."""

    __tablename__ = "lineage_events"
    event_id: Mapped[str] = mapped_column(String, primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class TaskRow(Base):
    """Internal persistence record for task facts."""

    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    state: Mapped[str] = mapped_column(String, default="QUEUED")
    queue: Mapped[str] = mapped_column(String, default="cpu")
    pipeline: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())
    finished_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_shards: Mapped[int] = mapped_column(Integer, default=1)
    error: Mapped[str | None] = mapped_column(String, nullable=True)
    input_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kg_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    datasheet_job_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)


class ShardRow(Base):
    """Internal persistence record for shard facts."""

    __tablename__ = "task_shards"
    __table_args__ = (UniqueConstraint("task_id", "ordinal"),)
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String, default="QUEUED", index=True)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON)
    outputs: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    lease_owner: Mapped[str | None] = mapped_column(String, nullable=True)
    heartbeat_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class OutboxRow(Base):
    """Internal persistence record for outbox facts."""

    __tablename__ = "outbox"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    delivered: Mapped[bool] = mapped_column(default=False, index=True)


class MetadataChangeRow(Base):
    """Internal persistence record for metadatachange facts."""

    __tablename__ = "metadata_changes"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    field: Mapped[str] = mapped_column(String)
    before: Mapped[Any] = mapped_column(JSON, nullable=True)
    after: Mapped[Any] = mapped_column(JSON, nullable=True)
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    occurred_at: Mapped[float] = mapped_column(Float, default=lambda: utcnow().timestamp())


class Database:
    """Own a database engine and short-lived transactional sessions."""

    def __init__(self, url: str | None = None) -> None:
        """Connect to the selected local or explicitly configured database."""
        url = url or get_settings().database_url or f"sqlite:///{data_dir() / 'datakeel.db'}"
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+pg8000://", 1)
        self.engine: Engine = create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30}
            if url.startswith("sqlite")
            else {},
            pool_pre_ping=True,
        )
        self.sqlite = self.engine.dialect.name == "sqlite"
        if self.sqlite:

            @event.listens_for(self.engine, "connect")
            def configure(connection: sqlite3.Connection, _record: ConnectionPoolEntry) -> None:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA busy_timeout=30000")
                connection.execute("PRAGMA journal_mode=WAL")

        self.sessions = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        """Create a session whose caller owns commit or rollback."""
        return self.sessions()

    def migrate(self) -> None:
        """Initialize tables and safely append nullable columns under one migration lock."""
        with self.engine.begin() as connection:
            if self.sqlite:
                connection.execute(text("BEGIN IMMEDIATE"))
            else:
                connection.execute(
                    text(
                        "SELECT pg_advisory_xact_lock("
                        "hashtext('datakeel:migrate:' || current_schema()))"
                    )
                )
            Base.metadata.create_all(connection)
            add_nullable_columns(connection)
            install_evidence_constraints(connection, sqlite=self.sqlite)
            if self.sqlite:
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        text(
                            f"CREATE TRIGGER IF NOT EXISTS lineage_no_{operation.lower()} "
                            f"BEFORE {operation} ON lineage_events BEGIN "
                            "SELECT RAISE(ABORT, 'lineage events are append-only'); END"
                        )
                    )
            else:
                connection.execute(
                    text("""
                    CREATE OR REPLACE FUNCTION datakeel_immutable_event() RETURNS trigger AS $$
                    BEGIN RAISE EXCEPTION 'lineage events are append-only'; END;
                    $$ LANGUAGE plpgsql
                """)
                )
                connection.execute(
                    text("""
                    DO $$ BEGIN IF NOT EXISTS (
                        SELECT 1 FROM pg_trigger WHERE tgname = 'datakeel_lineage_immutable'
                        AND tgrelid = 'lineage_events'::regclass
                    ) THEN CREATE TRIGGER datakeel_lineage_immutable
                    BEFORE UPDATE OR DELETE ON lineage_events FOR EACH ROW
                    EXECUTE FUNCTION datakeel_immutable_event(); END IF; END $$
                """)
                )

    def lock_writes(self, session: Session) -> None:
        """Serialize SQLite writers to match PostgreSQL row-lock semantics."""
        if self.sqlite:
            session.execute(text("BEGIN IMMEDIATE"))
