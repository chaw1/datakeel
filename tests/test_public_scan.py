# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Temporary Git repositories exercise complete historical scans and binary classification."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from scripts import public_scan
from scripts.public_scan import MAX_BLOB_BYTES, scan_repository
from tests.test_public_scan_rules import email, local_path

if TYPE_CHECKING:
    from pathlib import Path


def git(repo: Path, *arguments: str) -> str:
    """Run Git only against a generated temporary repository with no remote."""
    return subprocess.run(  # noqa: S603  # Test-owned argument array, never a shell.
        ["git", "-C", str(repo), *arguments],  # noqa: S607  # Git is the exercised maintainer tool.
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.strip()


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    """Initialize a private test repository with the approved public contributor identity."""
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "chaw1")
    git(tmp_path, "config", "user.email", "34927473+chaw1@users.noreply.github.com")
    return tmp_path


def commit(repo: Path, message: str = "test: generated sample") -> str:
    """Commit the generated fixture tree and return its immutable identity."""
    git(repo, "add", "--all")
    git(repo, "commit", "--allow-empty", "-qm", message)
    return git(repo, "rev-parse", "HEAD")


def test_deleted_historical_file_remains_detected(repository: Path) -> None:
    """A clean tip cannot conceal a sensitive value removed from an older commit."""
    path = repository / "old.txt"
    path.write_text("first line\n" + local_path() + "\n")
    first = commit(repository)
    path.unlink()
    second = commit(repository)
    report = scan_repository(repository, ())
    assert report.scanned_commits == 2
    assert [(item.commit, item.path, item.line, item.rule) for item in report.findings] == [
        (first, "old.txt", 2, "local_path")
    ]
    assert second not in {item.commit for item in report.findings}
    assert local_path() not in report.model_dump_json()


def test_cached_blob_is_reported_in_every_commit_and_path(repository: Path) -> None:
    """Caching saves object reads while preserving all historical references to a finding."""
    content = ("AK" + "IA" + "Z" * 16).encode()
    (repository / "first.txt").write_bytes(content)
    first = commit(repository)
    (repository / "second.txt").write_bytes(content)
    second = commit(repository)
    report = scan_repository(repository, ())
    assert report.scanned_blobs == 1
    assert {(item.commit, item.path) for item in report.findings} == {
        (first, "first.txt"),
        (second, "first.txt"),
        (second, "second.txt"),
    }
    assert content.decode() not in report.model_dump_json()


def test_all_branches_and_tagged_commits_are_scanned(repository: Path) -> None:
    """Reachable history outside the current branch is never silently skipped."""
    safe = commit(repository)
    git(repository, "checkout", "-qb", "generated-other")
    (repository / "side.txt").write_text(local_path())
    leaked = commit(repository)
    git(repository, "tag", "generated-tag")
    git(repository, "checkout", "-q", "--detach", safe)
    git(repository, "branch", "-D", "generated-other")
    report = scan_repository(repository, ())
    assert report.scanned_commits == 2
    assert report.findings[0].commit == leaked


def test_file_names_and_excluded_directories_are_scanned(repository: Path) -> None:
    """Even binary data cannot hide a forbidden filename or surviving excluded entry."""
    directory = "docs/" + "co" + "dex/"
    target = repository / directory / "note.md"
    target.parent.mkdir(parents=True)
    target.write_text("safe")
    forbidden_name = "solar" + "sense" + ".png"
    (repository / forbidden_name).write_bytes(b"\x89PNG\r\n\x1a\n")
    (repository / "generated.log").write_text("safe")
    commit(repository)
    report = scan_repository(repository, (directory, "*.log"))
    assert {(item.path, item.rule) for item in report.findings} == {
        (directory + "note.md", "excluded_path"),
        ("generated.log", "excluded_path"),
        (forbidden_name, "internal_name"),
    }


@pytest.mark.parametrize("signature", [b"\x89PNG\r\n\x1a\n", b"wOF2", b"\xff\xd8\xff"])
def test_binary_magic_skips_text_rules_without_relying_on_filename(
    repository: Path, signature: bytes
) -> None:
    """Recognized binary assets get size checks even with a misleading text suffix."""
    (repository / "binary.txt").write_bytes(signature + local_path().encode())
    (repository / "disguised.png").write_text(local_path())
    commit(repository)
    report = scan_repository(repository, ())
    assert [(item.path, item.rule) for item in report.findings] == [("disguised.png", "local_path")]
    assert report.images == (() if signature == b"wOF2" else ("binary.txt",))


def test_all_historical_images_are_reported_including_removed_paths(repository: Path) -> None:
    """Reviewers can inspect image names even when those images no longer exist at the tip."""
    first = repository / "first.bin"
    first.write_bytes(b"GIF89a" + b"\0" * 20)
    commit(repository)
    first.unlink()
    (repository / "vector.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"></svg>')
    commit(repository)
    report = scan_repository(repository, ())
    assert report.images == ("first.bin", "vector.svg")
    assert report.findings == ()


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32", "utf-8-sig"])
def test_unicode_text_with_byte_order_mark_is_not_misclassified_as_binary(
    repository: Path, encoding: str
) -> None:
    """Nul bytes in a supported Unicode encoding do not conceal sensitive text."""
    (repository / "unicode.txt").write_bytes(("safe\n" + local_path()).encode(encoding))
    commit(repository)
    report = scan_repository(repository, ())
    assert [(item.line, item.rule) for item in report.findings] == [(2, "local_path")]


def test_legacy_encoded_text_still_exposes_ascii_sensitive_values(repository: Path) -> None:
    """Unknown non-NUL encodings remain text so a single non-UTF byte cannot conceal a leak."""
    source = "café\n" + local_path() + "\nto" + "ken=generated\n"
    (repository / "legacy.txt").write_bytes(source.encode("latin-1"))
    commit(repository)
    report = scan_repository(repository, ())
    assert [(item.line, item.rule) for item in report.findings] == [
        (2, "local_path"),
        (3, "secret"),
    ]


def test_blob_size_boundary_covers_binary_and_text(repository: Path) -> None:
    """Exactly the size limit passes; one extra byte fails for every file type."""
    (repository / "at-limit.txt").write_bytes(b"a" * MAX_BLOB_BYTES)
    (repository / "too-large.bin").write_bytes(b"wOF2" + b"\0" * (MAX_BLOB_BYTES - 3))
    commit(repository)
    report = scan_repository(repository, ())
    assert [(item.path, item.rule, item.line) for item in report.findings] == [
        ("too-large.bin", "oversized_blob", 1)
    ]


def test_commit_message_and_both_identities_are_scanned(repository: Path) -> None:
    """Commit-only process vocabulary and private contributor identities have explicit locations."""
    git(repository, "config", "user.email", email())
    commit(repository, "docs: " + "co" + "dex")
    report = scan_repository(repository, ())
    assert {(item.path, item.rule) for item in report.findings} == {
        ("<commit-message>", "commit_message"),
        ("<author>", "email"),
        ("<committer>", "email"),
    }
    assert email() not in report.model_dump_json()


def test_current_scanner_and_tests_do_not_embed_sensitive_samples(repository: Path) -> None:
    """The detector and its tests must remain publishable under their own content rules."""
    source_root = public_scan.__file__
    assert source_root is not None
    root = repository.__class__(source_root).resolve().parents[1]
    files = (*root.glob("scripts/public_scan*.py"), *root.glob("tests/test_public_scan*.py"))
    for source in files:
        target = repository / source.relative_to(root)
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(source.read_bytes())
    commit(repository)
    report = scan_repository(repository, ())
    assert report.findings == ()


def test_git_environment_cannot_redirect_the_scan(
    repository: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ambient Git state cannot substitute another worktree, namespace or config for the target."""
    commit(repository)
    outside = repository / "untracked-other"
    outside.mkdir()
    git(outside, "init", "-q")
    git(outside, "config", "user.name", "chaw1")
    git(outside, "config", "user.email", "chaw1@users.noreply.github.com")
    (outside / "leak.txt").write_text(local_path())
    commit(outside)
    monkeypatch.setenv("GIT_DIR", str(outside / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(outside))
    monkeypatch.setenv("GIT_NAMESPACE", "nonexistent")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.repositoryformatversion")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "invalid")
    report = scan_repository(repository, ())
    assert report.scanned_commits == 1
    assert report.findings == ()


def test_replacement_objects_cannot_hide_original_sensitive_history(repository: Path) -> None:
    """Replace refs cannot alter the original objects being scanned."""
    path = repository / "leak.txt"
    path.write_text(local_path())
    sensitive = commit(repository)
    path.unlink()
    clean = commit(repository)
    tree = git(repository, "rev-parse", clean + "^{tree}")
    replacement = git(repository, "commit-tree", tree, "-m", "test: generated replacement")
    git(repository, "replace", sensitive, replacement)
    report = scan_repository(repository, ())
    assert any(item.commit == sensitive and item.rule == "local_path" for item in report.findings)
