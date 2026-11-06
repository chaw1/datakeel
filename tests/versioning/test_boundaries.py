# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Maintenance location, ephemeral fixtures, safe configuration and package boundaries."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from urllib.parse import urlencode, urlunsplit
from uuid import uuid4

import pytest
from sqlalchemy import create_engine

from datakeel.core.errors import ValidationError
from datakeel.core.settings import Settings
from datakeel.storage.database import Database
from datakeel.versioning import initialize, require_current
from datakeel.versioning.configuration import write_configuration
from datakeel.versioning.location import readonly_engine, sqlite_path
from datakeel.versioning.recovery import contained

if TYPE_CHECKING:
    from pathlib import Path


def test_explicit_memory_fixture_initialization_and_reader_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Memory fixtures initialize explicitly; service startup and repeats never upgrade."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path))
    database = Database("sqlite://")
    try:
        with pytest.raises(ValidationError, match="not current"):
            require_current(database)
        initialize(database)
        require_current(database)
        initialize(database)
    finally:
        database.engine.dispose()
    assert not (tmp_path / "backups").exists()


@pytest.mark.parametrize(
    "url",
    [
        "sqlite://",
        "sqlite:///:memory:",
        "sqlite:///local?mode=rw",
        "postgresql://database.example.test/facts",
    ],
)
def test_unsupported_location_rejected_without_backend_probe(url: str) -> None:
    """Memory, URL options and PostgreSQL never fall through to file creation or connections."""
    with pytest.raises(ValidationError):
        sqlite_path(url)


def test_readonly_uri_preserves_special_filename_and_blocks_writes(tmp_path: Path) -> None:
    """A filename containing URI punctuation remains a filename under mandatory mode=ro."""
    path = tmp_path / "database #?%.sqlite"
    from sqlalchemy.engine import URL  # noqa: PLC0415
    from sqlalchemy.exc import SQLAlchemyError  # noqa: PLC0415

    engine = create_engine(URL.create("sqlite", database=str(path)))
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE fixture (value TEXT)")
    engine.dispose()
    engine = readonly_engine(path)
    try:
        with engine.connect() as connection, pytest.raises(SQLAlchemyError, match="readonly"):
            connection.exec_driver_sql("INSERT INTO fixture VALUES ('blocked')")
    finally:
        engine.dispose()


def test_configuration_contains_routing_and_addresses_but_no_credentials(tmp_path: Path) -> None:
    """Keep recoverable routing contents and named secret references."""
    routing = tmp_path / "models.yaml"
    routing.write_text("version: 1\nproviders: {}\nendpoints: {}\n")
    credential = uuid4().hex
    settings = Settings(
        home=tmp_path,
        model_routing_file=routing,
        openai_base_url=urlunsplit(
            (
                "https",
                f"user:{credential}@models.example.test",
                "/api",
                urlencode({"token": credential}),
                "private",
            )
        ),
        openai_api_key="generated-test-key",
    )
    references = write_configuration(settings, tmp_path)
    document = json.loads((tmp_path / "config.json").read_text())
    assert document["model_routing"] == {"version": 1, "providers": {}, "endpoints": {}}
    assert document["settings"]["openai_base_url"] == "https://models.example.test/api"
    assert document["settings"]["home"] == "."
    assert document["settings"]["database_url"] == "sqlite:///datakeel.db"
    assert "openai_api_key" in references
    assert "openai_base_url.credentials" in references
    assert credential not in (tmp_path / "config.json").read_text()
    assert "generated-test-key" not in (tmp_path / "config.json").read_text()


@pytest.mark.parametrize("contents", ["[invalid", "unexpected_secret: do-not-disclose"])
def test_bad_routing_configuration_fails_without_echoing_contents(
    tmp_path: Path, contents: str
) -> None:
    """Invalid configuration cannot enter a recovery package or leak values into its error."""
    path = tmp_path / "models.yaml"
    path.write_text(contents)
    with pytest.raises(ValidationError, match="Invalid non-secret routing configuration") as error:
        write_configuration(Settings(home=tmp_path, model_routing_file=path), tmp_path)
    assert contents not in str(error.value)
    assert not (tmp_path / "config.json").exists()


@pytest.mark.parametrize("relative", ["../escape", "/absolute", "bad\\key"])
def test_unsafe_recovery_component_paths_fail_closed(tmp_path: Path, relative: str) -> None:
    """Package members cannot escape either the original object root or the restored home."""
    with pytest.raises(ValidationError, match="Unsafe recovery file path"):
        contained(tmp_path, relative)


def test_maintenance_json_schema_matches_frozen_contract() -> None:
    """CLI reports cannot silently change their field types, required fields or enum meanings."""
    from pathlib import Path  # noqa: PLC0415

    from datakeel.versioning.models import DatabaseStatus  # noqa: PLC0415

    contract = Path("contracts/persistence/database-status.schema.json")
    assert DatabaseStatus.model_json_schema() == json.loads(contract.read_text())


def test_schema_comparison_keeps_whitespace_inside_check_literals(tmp_path: Path) -> None:
    """Different CHECK literals must not collapse into the same semantic baseline."""
    from datakeel.versioning.inspect import validate_baseline  # noqa: PLC0415
    from datakeel.versioning.models import BaselineDefinition, SchemaObject  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'literal.db'}")
    expected = "CREATE TABLE sample (label TEXT CHECK(label <> 'two  spaces'))"
    baseline = BaselineDefinition(
        id="literal",
        objects=(SchemaObject(kind="table", name="sample", table="sample", sql=expected),),
    )
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(expected.replace("two  spaces", "two spaces"))
            with pytest.raises(ValidationError, match="baseline mismatch"):
                validate_baseline(connection, baseline)
    finally:
        engine.dispose()


def test_fact_fingerprint_distinguishes_blob_from_lookalike_text(tmp_path: Path) -> None:
    """A BLOB-to-text rewrite cannot hide behind a string rendering in fact preservation."""
    from datakeel.versioning.inspect import facts_digest  # noqa: PLC0415

    engine = create_engine(f"sqlite:///{tmp_path / 'blob.db'}")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE sample (value BLOB)")
            connection.exec_driver_sql("INSERT INTO sample VALUES (?)", (b"binary",))
            before = facts_digest(connection)
            connection.exec_driver_sql("UPDATE sample SET value=?", (str(b"binary"),))
            assert facts_digest(connection) != before, "W4-blob-type-preservation"
    finally:
        engine.dispose()
