# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exercise current-file privacy gates independently of committed history and staging."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts.check_public_worktree import main
from scripts.public_scan import MAX_BLOB_BYTES, scan_worktree
from tests.test_public_scan import commit, git
from tests.test_public_scan_rules import address, email, local_path

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Initialize an isolated worktree with the same public identity used by history tests."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "chaw1")
    git(tmp_path, "config", "user.email", "chaw1@users.noreply.github.com")
    return tmp_path


def test_worktree_uses_unstaged_contents_and_includes_untracked_files(repository: Path) -> None:
    """A staged safe blob must not hide a changed working file or an untracked sibling."""
    tracked = repository / "tracked.txt"
    tracked.write_text("safe")
    commit(repository)
    tracked.write_text("first\n" + local_path() + "\n")
    (repository / "untracked.txt").write_text("first\nsecond\n" + email())
    report = scan_worktree(repository)
    assert {(item.path, item.line, item.rule) for item in report.findings} == {
        ("tracked.txt", 2, "local_path"),
        ("untracked.txt", 3, "email"),
    }
    assert report.scanned_blobs == 2
    assert local_path() not in report.model_dump_json()
    assert email() not in report.model_dump_json()


def test_ignored_untracked_files_and_deleted_entries_are_skipped(repository: Path) -> None:
    """Local generated data is ignored while forced tracked files remain subject to scanning."""
    (repository / ".gitignore").write_text("*.local\n")
    removed = repository / ("solar" + "sense" + ".txt")
    removed.write_text("safe")
    tracked = repository / "tracked.local"
    tracked.write_text("safe")
    git(repository, "add", "-f", "tracked.local")
    commit(repository)
    removed.unlink()
    tracked.write_text(local_path())
    (repository / "ignored.local").write_text(email())
    report = scan_worktree(repository)
    assert [(item.path, item.rule) for item in report.findings] == [("tracked.local", "local_path")]
    assert report.scanned_blobs == 2


def test_worktree_reuses_network_secret_name_and_unicode_rules(repository: Path) -> None:
    """History and worktree checks share sensitive-value detection and exact source locations."""
    source = "\n".join((address(10, 0, 0, 1), "s" + "k-" + "a" * 24, "Solar" + "Sense"))
    (repository / "unicode.txt").write_bytes(source.encode("utf-16"))
    assert [(item.line, item.rule) for item in scan_worktree(repository).findings] == [
        (1, "private_ip"),
        (2, "secret"),
        (3, "internal_name"),
    ]


def test_worktree_binary_size_and_filename_rules_are_preserved(repository: Path) -> None:
    """Binary contents are not decoded while their filenames and size remain checked."""
    name = "solar" + "sense" + ".png"
    (repository / name).write_bytes(b"\x89PNG\r\n\x1a\n" + local_path().encode())
    (repository / "large.bin").write_bytes(b"wOF2" + b"\0" * MAX_BLOB_BYTES)
    report = scan_worktree(repository)
    assert {(item.path, item.rule) for item in report.findings} == {
        (name, "internal_name"),
        ("large.bin", "oversized_blob"),
    }
    assert report.images == (name,)


def test_worktree_symlinks_are_scanned_without_reading_external_targets(repository: Path) -> None:
    """Scan link text only, even when an external target exists and contains sensitive text."""
    external = repository.parent / (repository.name + "-external.txt")
    external.write_text(email())
    (repository / "safe-link").symlink_to("../" + external.name)
    (repository / "private-link").symlink_to(local_path())
    assert [(item.path, item.rule) for item in scan_worktree(repository).findings] == [
        ("private-link", "local_path")
    ]


def test_worktree_does_not_follow_replaced_parent_directory(repository: Path) -> None:
    """Replacing a tracked directory with a symlink must not make the scanner read outside."""
    directory = repository / "tracked"
    directory.mkdir()
    child = directory / "child.txt"
    child.write_text("safe")
    commit(repository)
    child.unlink()
    directory.rmdir()
    external = repository.parent / (repository.name + "-external")
    external.mkdir()
    (external / "child.txt").write_text(email())
    directory.symlink_to(external, target_is_directory=True)
    report = scan_worktree(repository)
    assert any(
        item.path == "tracked/child.txt" and item.rule == "unsupported_entry"
        for item in report.findings
    )
    assert not any(item.rule == "email" for item in report.findings)


def test_worktree_cli_reports_locations_and_failure_without_values(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command used by make returns failure and reviewable redacted locations."""
    (repository / "sample.txt").write_text("safe\n" + email())
    monkeypatch.chdir(repository)
    with pytest.raises(SystemExit) as error:
        main()
    output = capsys.readouterr().out
    assert error.value.code == 1
    assert "sample.txt:2: email" in output
    assert email() not in output


def test_worktree_cli_passes_reserved_domain_samples(
    repository: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A generated sample remains valid in the exact CLI used by local and CI quality gates."""
    (repository / "sample.txt").write_text("sample@example.org")
    monkeypatch.chdir(repository)
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 0
    assert "1 files, 0 findings" in capsys.readouterr().out
