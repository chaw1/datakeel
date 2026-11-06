# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reject Row leaks, unlisted transitional edges and schema ratchet drift."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts import check_boundaries, check_schema


def test_dataset_rows_count_once_in_the_dataset_slice_budget() -> None:
    """Moved dataset Rows cannot consume the original schema composition budget too."""
    rows = Path("datakeel/dataset_store/rows.py")
    assert rows in check_schema._dataset_slice_paths()  # noqa: SLF001
    assert rows not in check_schema._schema_paths()  # noqa: SLF001
    assert Path("datakeel/dataset_store/schema.py") in check_schema._schema_paths()  # noqa: SLF001


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


def test_physical_row_module_cannot_bypass_canonical_import_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Moving a Row into a private submodule cannot create an unlisted legacy exception."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/storage/adapter.py"
    path.parent.mkdir(parents=True)
    path.write_text("from datakeel.dataset_store.file_rows import FileStateRow\n")
    allowed = {"datakeel/storage/adapter.py": {"datakeel.dataset_store.rows": ["FileStateRow"]}}
    assert check_schema._row_import_violations(allowed)  # noqa: SLF001  # Exercise the gate.


@pytest.mark.parametrize("package", ["storage", "domain"])
@pytest.mark.parametrize(
    "source",
    [
        "from datakeel.dataset_store import rows\nvalue = rows.UploadRow\n",
        "import datakeel.dataset_store.rows as rows\nvalue = rows.UploadRow\n",
        "from datakeel.dataset_store import rows as records\nvalue = records.UploadRow\n",
        "import datakeel.dataset_store.rows as records\nvalue = records.UploadRow\n",
        "import datakeel.dataset_store.rows\nvalue = datakeel.dataset_store.rows.UploadRow\n",
        "from datakeel import dataset_store as store\nvalue = store.rows.UploadRow\n",
    ],
)
def test_module_style_rows_require_an_explicit_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str, package: str
) -> None:
    """Resolve real alias attribute uses in legacy adapters and public modules alike."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / f"datakeel/{package}/adapter.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    assert check_schema._row_import_violations({})  # noqa: SLF001  # Exercise the gate.
    if package == "domain":
        assert check_boundaries.violations()
    allowed = {f"datakeel/{package}/adapter.py": {"datakeel.dataset_store.rows": ["UploadRow"]}}
    assert not check_schema._row_import_violations(allowed)  # noqa: SLF001


def test_module_import_without_row_use_does_not_consume_a_row_allowance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only actual Row references require inventory entries, including direct aliases."""
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "datakeel/storage/adapter.py"
    path.parent.mkdir(parents=True)
    path.write_text(
        "from datakeel.dataset_store import rows as records\n"
        "from datakeel.dataset_store.rows import DatasetRow as Record\n"
    )
    allowed = {"datakeel/storage/adapter.py": {"datakeel.dataset_store.rows": ["DatasetRow"]}}
    assert not check_schema._row_import_violations(allowed)  # noqa: SLF001


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
