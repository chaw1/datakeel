# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject Row leaks, unlisted transitional edges and schema ratchet drift."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts import check_boundaries, check_schema

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_new_store_rows_cannot_enter_pure_or_public_modules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """New schema packages get the same Row boundary protection as legacy storage."""
    monkeypatch.chdir(tmp_path)
    module = tmp_path / "datakeel/domain/port.py"
    module.parent.mkdir(parents=True)
    module.write_text("from datakeel.dataset_store.rows import DatasetRow\n")
    assert len(check_boundaries.violations()) == 1


def test_only_listed_legacy_adapters_can_import_new_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An existing legacy allowance cannot authorize another module or Row type."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/storage/adapter.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.dataset_store.rows import DatasetRow, VersionRow\n")
    allowed = {"datakeel/storage/adapter.py": {"datakeel.dataset_store.rows": ["DatasetRow"]}}
    assert check_schema._row_import_violations(allowed)  # noqa: SLF001  # Static gate unit boundary.
    allowed["datakeel/storage/adapter.py"]["datakeel.dataset_store.rows"].append("VersionRow")
    assert not check_schema._row_import_violations(allowed)  # noqa: SLF001


def test_database_cannot_regain_domain_imports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Central Row definitions and installer imports are both rejected."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/storage/database.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.dataset_store.schema import SCHEMA\nclass DatasetRow: pass\n")
    assert len(check_schema._database_violations()) == 2  # noqa: SLF001


def test_frozen_canonical_bytes_and_size_limits_are_independent_of_current_wiring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A changed canonical copy and an exceeded quota each make the gate red."""
    baseline = json.loads(check_schema.BASELINE.read_text())
    baseline["measurements"]["storage_lines"] = 0
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline))
    monkeypatch.setattr(check_schema, "BASELINE", path)
    canonical = tmp_path / "canonical.json"
    canonical.write_text("[]")
    monkeypatch.setattr(check_schema, "CANONICAL", canonical)
    problems = check_schema.violations()
    assert "Frozen canonical table-owner artifact changed" in problems
    assert any("storage_lines" in problem for problem in problems)


def test_vector_increment_keeps_unlisted_transitional_rows_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A named E2 adapter allowance cannot authorize an unrelated worker Row."""
    from scripts.schema_extensions import extension  # noqa: PLC0415  # Read before chdir.

    allowed = extension().legacy_row_imports
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/storage/vector_planning.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.worker_store.rows import ShardRow\n")
    assert check_schema._row_import_violations(allowed)  # noqa: SLF001


def test_vector_owner_copy_has_its_own_frozen_digest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unchanged legacy digest cannot mask drift in the separate vector inventory."""
    from scripts import schema_extensions  # noqa: PLC0415  # Isolate the extension oracle.

    increment = schema_extensions.extension()
    path = tmp_path / "vector_tables.json"
    path.write_text("[]")
    monkeypatch.setattr(schema_extensions, "VECTOR_CANONICAL", path)
    assert schema_extensions.canonical_violations(increment)


def test_vector_composition_row_allowance_is_file_scoped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The vector composition root does not exempt the whole persistence package."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/persistence/unlisted.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.storage.vector_rows import VectorAccountRow\n")
    assert len(check_boundaries.violations()) == 1
