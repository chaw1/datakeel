# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Batch object access preserves identities, current settings and path containment."""

from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.storage.datasets import materialize_files, persist_files
from datakeel.storage.objects import LocalStore


def test_batch_preserves_distinct_identities_for_shared_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Shared content resolves once without collapsing manifest entries or caching reads."""
    monkeypatch.setenv("DATAKEEL_HOME", str(tmp_path / "home"))
    source = tmp_path / "source.txt"
    source.write_text("shared content")
    stored = persist_files(
        [
            FileItem(id=identifier, path=str(source), filename=identifier)
            for identifier in ("a", "b")
        ]
    )
    calls: list[str] = []
    original = LocalStore.materialize

    def materialize(store: LocalStore, key: str) -> Path:
        calls.append(key)
        return original(store, key)

    monkeypatch.setattr(LocalStore, "materialize", materialize)
    restored = materialize_files(stored)
    assert [item.id for item in restored] == ["a", "b"]
    assert restored[0].path == restored[1].path
    assert len(calls) == 1
    Path(restored[0].path).unlink()
    with pytest.raises(FileNotFoundError):
        materialize_files(stored)


def test_each_batch_uses_current_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Changing process configuration between operations must select a fresh backend."""
    source = tmp_path / "source.txt"
    source.write_text("generated data")
    item = FileItem(path=str(source), filename=source.name)
    for name in ("first", "second"):
        home = tmp_path / name
        monkeypatch.setenv("DATAKEEL_HOME", str(home))
        restored = materialize_files(persist_files([item]))
        assert Path(restored[0].path).is_relative_to(home)
        assert Path(restored[0].path).read_text() == "generated data"


def test_local_store_rechecks_object_symlinks(tmp_path: Path) -> None:
    """Resolving the root once must still reject a key redirected outside that root."""
    store = LocalStore(tmp_path / "objects")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside")
    (store.root / "linked.txt").symlink_to(outside)
    with pytest.raises(ValidationError, match="outside store"):
        store.materialize("linked.txt")
