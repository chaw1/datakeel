# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actual DDL/data/ledger failures, process death, maintenance exclusion and valid prefixes."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import create_engine

from datakeel.core.settings import Settings
from datakeel.versioning.campaign import status, upgrade
from tests.versioning.helpers import seed_toy, toy_registry

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.versioning.models import MigrationDefinition


def _child(path: Path, home: Path, fault: str) -> subprocess.CompletedProcess[str]:
    script = (
        "from pathlib import Path; from tests.versioning.helpers import run_toy; "
        f"raise SystemExit(run_toy(Path({str(path)!r}), Path({str(home)!r}), {fault!r}))"
    )
    return subprocess.run(  # noqa: S603  # Fixed local fixture subprocess, no services.
        [sys.executable, "-c", script], capture_output=True, text=True, check=False, timeout=30
    )


def oracle(path: Path) -> None:
    """Assert frozen complete fields and audit sequence; never derive expected from handlers."""
    engine = create_engine(f"sqlite:///{path}")
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT * FROM items ORDER BY id").fetchall() == [
                (1, "ONE", "converted"),
                (2, "TWO", "converted"),
            ], "W4-facts-full-fields-and-identities"
            assert connection.exec_driver_sql("SELECT * FROM audit ORDER BY seq").fetchall() == [
                (1, "original"),
                (2, "converted"),
            ], "W4-audit-sequence"
    finally:
        engine.dispose()


@pytest.mark.parametrize("fault", ["ddl", "data", "ledger", "die-ddl", "die-data", "die-ledger"])
def test_failure_or_death_rolls_back_real_second_version_and_resumes_one_package(
    tmp_path: Path, fault: str
) -> None:
    """The first commit survives; every later failure leaves no partial DDL/data/ledger."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    failed = _child(path, home, fault)
    assert failed.returncode == (73 if fault.startswith("die-") else 5), failed.stderr
    if not fault.startswith("die-"):
        assert json.loads(failed.stdout)["error"] == "Version 2 failed (RuntimeError)", (
            "W4-injected-stage-reached-before-failure"
        )
    report = status(path, home, toy_registry())
    assert (report.version, report.pending) == (1, (2,))
    engine = create_engine(f"sqlite:///{path}")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT * FROM items ORDER BY id").fetchall() == [
            (1, "one"),
            (2, "two"),
        ], "W4-failure-full-rollback"
        assert connection.exec_driver_sql("SELECT * FROM audit").fetchall() == [(1, "original")]
        assert (
            connection.exec_driver_sql("SELECT count(*) FROM datakeel_schema_versions").scalar()
            == 1
        )
    engine.dispose()
    package = next((home / "backups").iterdir())
    before = {p.name: p.read_bytes() for p in package.iterdir() if p.is_file()}
    resumed = upgrade(path, Settings(home=home), toy_registry())
    assert resumed.exit_code == 0
    assert resumed.applied == (2,)
    oracle(path)
    assert upgrade(path, Settings(home=home), toy_registry()).applied == ()
    assert list((home / "backups").iterdir()) == [package]
    assert {p.name: p.read_bytes() for p in package.iterdir() if p.is_file()} == before


def test_campaign_lock_survives_first_commit_and_waiter_only_reads_final_head(
    tmp_path: Path,
) -> None:
    """Two processes contend across version commits; waiter cannot back up or reapply writes."""
    path, home, barrier = tmp_path / "db", tmp_path / "home", tmp_path / "barrier"
    seed_toy(path)
    script = f"""
import time
from pathlib import Path
from datakeel.versioning import campaign
from tests.versioning.helpers import run_toy
original = campaign.apply_version
def apply(c, definition, name):
    original(c, definition, name)
    if definition.version == 1:
        Path({str(barrier)!r}).touch()
        time.sleep(1)
campaign.apply_version = apply
raise SystemExit(run_toy(Path({str(path)!r}), Path({str(home)!r})))
"""
    with subprocess.Popen(  # noqa: S603  # Local, owned SQLite subprocess only.
        [sys.executable, "-c", script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    ) as leader:
        deadline = time.monotonic() + 15
        while not barrier.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert barrier.exists(), leader.communicate(timeout=5)
        began = time.monotonic()
        waiter = _child(path, home, "")
        assert time.monotonic() - began > 0.5, "W4-lock-held-between-commits"
        _, errors = leader.communicate(timeout=10)
        assert leader.returncode == waiter.returncode == 0, (errors, waiter.stderr)
    oracle(path)
    assert len(list((home / "backups").iterdir())) == 1


@pytest.mark.parametrize("bad", ["commit", "pragma", "facts", "postcondition"])
def test_handler_cannot_escape_transaction_or_silently_change_facts(
    tmp_path: Path, bad: str
) -> None:
    """Transaction control, unexpected data and mismatched target schemas all roll back."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    versions = toy_registry()
    sql = {
        "commit": "COMMIT",
        "pragma": "PRAGMA user_version=7",
        "facts": "UPDATE items SET label='changed'",
        "postcondition": "CREATE TABLE extra (id INT)",
    }[bad]
    altered: MigrationDefinition = versions[0].model_copy(
        update={
            "forward": lambda connection: connection.exec_driver_sql(sql),
        }
    )
    report = upgrade(path, Settings(home=home), (altered, versions[1]))
    assert report.exit_code == 5
    assert status(path, home, versions).version == 0


@pytest.mark.parametrize(
    ("mutation", "anchor"),
    [
        ("UPDATE items SET note='bad' WHERE id=1", "W4-facts-full-fields-and-identities"),
        ("DELETE FROM items WHERE id=1", "W4-facts-full-fields-and-identities"),
        (
            "UPDATE audit SET value=CASE seq WHEN 1 THEN 'converted' ELSE 'original' END",
            "W4-audit-sequence",
        ),
    ],
)
def test_independent_fact_mutations_killed_at_named_assertion(
    tmp_path: Path, mutation: str, anchor: str
) -> None:
    """Unauthorized fields, missing rows and reordered audit values reach exact oracle anchors."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    assert upgrade(path, Settings(home=home), toy_registry()).exit_code == 0
    oracle(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql(mutation)
    engine.dispose()
    with pytest.raises(AssertionError, match=anchor):
        oracle(path)


def test_explicit_target_prefix_and_no_downgrade_share_one_campaign(tmp_path: Path) -> None:
    """Stopping at a registered target leaves a legal prefix; extending it reuses recovery."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    settings = Settings(home=home)
    partial = upgrade(path, settings, toy_registry(), to=1)
    assert partial.exit_code == 0
    assert partial.version == 1
    assert partial.pending == (2,)
    complete = upgrade(path, settings, toy_registry(), to=2)
    assert complete.exit_code == 0
    assert complete.backup_manifest == partial.backup_manifest
    oracle(path)
    assert upgrade(path, settings, toy_registry(), to=1).exit_code == 2


def test_changed_facts_in_retry_campaign_rejected_before_second_handler(tmp_path: Path) -> None:
    """A valid prefix does not authorize reusing a recovery point after unrelated writes."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    assert upgrade(path, Settings(home=home), toy_registry("data")).exit_code == 5
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE items SET label='unrelated'")
    engine.dispose()
    result = upgrade(path, Settings(home=home), toy_registry())
    assert result.exit_code == 4
    assert result.version == 1


def test_same_structure_unauthorized_change_rejected_at_named_anchor(tmp_path: Path) -> None:
    """Data preservation is a migration postcondition even when the full target DDL matches."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    versions = toy_registry()
    changed = versions[0].model_copy(
        update={
            "forward": lambda connection: connection.exec_driver_sql(
                "UPDATE items SET label='mutated'"
            )
        }
    )
    result = upgrade(path, Settings(home=home), (changed, versions[1]), to=1)
    assert result.exit_code == 5, "W4-unauthorized-facts-rejected"


def test_unexpected_table_rejected_at_named_anchor(tmp_path: Path) -> None:
    """Unknown complete-table additions never become an implicitly supported baseline."""
    path, home = tmp_path / "db", tmp_path / "home"
    seed_toy(path)
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE unexpected (id INTEGER)")
    engine.dispose()
    assert status(path, home, toy_registry()).exit_code == 3, "W4-unknown-schema-rejected"
