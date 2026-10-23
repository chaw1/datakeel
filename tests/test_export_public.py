# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Public exports isolate source Git state and preserve reviewable history and scan reports."""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from scripts import export_public
from scripts.public_export_git import PUBLIC_EMAIL, PUBLIC_NAME, git
from scripts.public_export_models import ExportError, ExportOptions, ExportPolicy, ExportReport
from scripts.public_export_policy import read_policy
from scripts.public_scan_models import ScanFinding

if TYPE_CHECKING:
    from pathlib import Path


def commit(repository: Path, message: str) -> str:
    """Commit only generated fixture files in a temporary local repository."""
    git(repository, "add", ".")
    git(repository, "commit", "-m", message)
    return git(repository, "rev-parse", "HEAD")


def create_source(tmp_path: Path, *, legacy_identity: bool = False) -> Path:
    """Create independent history whose identities and contents never access existing services."""
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--initial-branch=main")
    email = "original" + "@" + "example.invalid" if legacy_identity else PUBLIC_EMAIL
    git(source, "config", "user.name", "Original Author" if legacy_identity else PUBLIC_NAME)
    git(source, "config", "user.email", email)
    git(source, "config", "commit.gpgsign", "false")
    (source / "README.md").write_text("A neutral data platform.\n")
    commit(source, "feat: initial platform")
    return source


def create_policy(tmp_path: Path, *, exclusions: tuple[str, ...] = ()) -> Path:
    """Keep injected maintenance policies outside generated source repositories."""
    directory = tmp_path / "policies"
    directory.mkdir()
    prefix = "public-"
    (directory / f"{prefix}exclude.txt").write_text("\n".join(exclusions) + "\n")
    (directory / f"{prefix}replace.txt").write_text("")
    (directory / f"{prefix}message-map.json").write_text("{}\n")
    (directory / f"{prefix}scan-allow.txt").write_text("")
    return directory


def source_state(source: Path) -> tuple[str, bytes, bytes]:
    """Fingerprint refs, the index, and working content without refreshing the source index."""
    return (
        git(source, "show-ref"),
        (source / ".git/index").read_bytes(),
        (source / "README.md").read_bytes(),
    )


def identity_filter(repository: Path, _policy: ExportPolicy, _temporary: Path) -> None:
    """Represent an unchanged filter result for a fixture already satisfying public policy."""
    mapping = repository / ".git/filter-repo"
    mapping.mkdir()
    commits = git(repository, "rev-list", "--all").splitlines()
    (mapping / "commit-map").write_text("old new\n" + "".join(f"{sha} {sha}\n" for sha in commits))


@pytest.mark.parametrize("mode", ["history", "snapshot"])
def test_local_export_accounts_for_history_without_installing_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Default tests exercise local clones, snapshots, scans, accounting, and report writing."""
    source = create_source(tmp_path)
    (source / "README.md").write_text("A second public revision.\n")
    commit(source, "docs: clarify introduction")
    policy_dir = create_policy(tmp_path)
    before = source_state(source)
    monkeypatch.setattr(export_public, "filter_history", identity_filter)
    options = ExportOptions.model_validate(
        {"source": source, "out": tmp_path / "output", "mode": mode, "policy_dir": policy_dir}
    )
    report = export_public.export_repository(options)
    assert report.success
    assert report.source_commit_count == 2
    assert report.deleted_empty_commit_count == 0
    assert report.retained_commit_count == (2 if mode == "history" else 1)
    assert report.collapsed_commit_count == (0 if mode == "history" else 1)
    assert report.scanned_commits == report.retained_commit_count
    assert source_state(source) == before
    assert not git(options.out, "remote")
    saved = ExportReport.model_validate_json(
        (options.out / ".git" / export_public.REPORT_FILENAME).read_text()
    )
    assert saved == report
    assert export_public.REPORT_FILENAME not in git(options.out, "ls-files")


def test_export_counts_a_deleted_empty_commit_from_the_filtered_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Accounting derives pruning from real filtered refs rather than message-map entry counts."""
    source = create_source(tmp_path)
    (source / "private").mkdir()
    (source / "private/notes.md").write_text("Generated private note.\n")
    removed = commit(source, "docs: private note")
    policy_dir = create_policy(tmp_path, exclusions=("private/",))

    def remove_private_tail(repository: Path, policy: ExportPolicy, temporary: Path) -> None:
        retained = git(repository, "rev-parse", "HEAD~1")
        git(repository, "reset", "--hard", retained)
        identity_filter(repository, policy, temporary)
        mapping = repository / ".git/filter-repo/commit-map"
        mapping.write_text(mapping.read_text() + f"{removed} {'0' * 40}\n")

    monkeypatch.setattr(export_public, "filter_history", remove_private_tail)
    report = export_public.export_repository(
        ExportOptions(source=source, out=tmp_path / "output", policy_dir=policy_dir)
    )
    assert report.success
    assert report.source_commit_count == 2
    assert report.deleted_empty_commit_count == report.retained_commit_count == 1
    assert report.collapsed_commit_count == 0


@pytest.mark.parametrize("mode", ["history", "snapshot"])
def test_export_fails_when_filtering_removes_all_public_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """An entirely removed source cannot yield a green empty history or an invented snapshot."""
    source = create_source(tmp_path)
    policy_dir = create_policy(tmp_path)

    def remove_all(repository: Path, _policy: ExportPolicy, _temporary: Path) -> None:
        git(repository, "update-ref", "-d", "refs/heads/main")

    monkeypatch.setattr(export_public, "filter_history", remove_all)
    options = ExportOptions.model_validate(
        {"source": source, "out": tmp_path / "output", "mode": mode, "policy_dir": policy_dir}
    )
    report = export_public.export_repository(options)
    assert not report.success
    assert report.errors == ("No public commits remain after filtering",)
    assert not git(options.out, "rev-list", "--all")


@pytest.mark.parametrize("kind", ["directory", "file", "symlink", "dangling-symlink", "inside"])
def test_export_refuses_existing_or_source_owned_destinations(tmp_path: Path, kind: str) -> None:
    """Existing data, symbolic targets, and the source worktree cannot become export storage."""
    source = create_source(tmp_path)
    output = tmp_path / "output"
    if kind == "directory":
        output.mkdir()
        (output / "keep.txt").write_text("existing work")
    elif kind == "file":
        output.write_text("existing work")
    elif kind.endswith("symlink"):
        output.symlink_to(source if kind == "symlink" else tmp_path / "missing")
    else:
        output = source / "new-output"
    before = source_state(source)
    with pytest.raises(ExportError):
        export_public.export_repository(ExportOptions(source=source, out=output))
    assert source_state(source) == before
    if kind == "directory":
        assert (output / "keep.txt").read_text() == "existing work"
    if kind == "inside":
        assert not output.exists()


def test_source_subdirectory_cannot_hide_source_owned_output(tmp_path: Path) -> None:
    """A source argument inside a repository is rejected before creating any destination."""
    source = create_source(tmp_path)
    nested = source / "nested"
    nested.mkdir()
    output = source / "sibling-output"
    with pytest.raises(ExportError, match="repository root"):
        export_public.export_repository(ExportOptions(source=nested, out=output))
    assert not output.exists()


def test_ignored_new_output_inside_source_preserves_tracked_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicitly ignored evidence directory can hold an export without changing tracked work."""
    source = create_source(tmp_path)
    (source / ".gitignore").write_text("evidence/\n")
    commit(source, "chore: ignore generated evidence")
    policy_dir = create_policy(tmp_path)
    before = source_state(source)
    monkeypatch.setattr(export_public, "filter_history", identity_filter)
    output = source / "evidence/public-history"
    report = export_public.export_repository(
        ExportOptions(source=source, out=output, policy_dir=policy_dir)
    )
    assert report.success
    assert source_state(source) == before
    assert not git(source, "ls-files", "--", "evidence")


def test_export_never_uses_git_metadata_as_output(tmp_path: Path) -> None:
    """Git metadata remains protected even if a broad ignore rule would otherwise match it."""
    source = create_source(tmp_path)
    (source / ".gitignore").write_text("*\n")
    with pytest.raises(ExportError, match="Git metadata"):
        export_public.export_repository(
            ExportOptions(source=source, out=source / ".git/new-output")
        )
    assert not (source / ".git/new-output").exists()


@pytest.mark.parametrize("failure", ["command", "timeout"])
def test_filter_failures_preserve_output_report_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    """Failed maintenance commands leave inspectable output and never rewrite source Git state."""
    source = create_source(tmp_path)
    before = source_state(source)
    policy_dir = create_policy(tmp_path)

    def fail_filter(_repository: Path, _policy: ExportPolicy, _temporary: Path) -> None:
        if failure == "timeout":
            command = "maintenance-tool"
            raise subprocess.TimeoutExpired(command, 180)
        msg = "Generated maintenance command failure"
        raise ExportError(msg)

    monkeypatch.setattr(export_public, "filter_history", fail_filter)
    output = tmp_path / "failed-output"
    report = export_public.export_repository(
        ExportOptions(source=source, out=output, policy_dir=policy_dir)
    )
    assert not report.success
    assert report.errors
    assert (output / ".git" / export_public.REPORT_FILENAME).is_file()
    assert (output / "README.md").read_bytes() == before[2]
    assert source_state(source) == before


@pytest.mark.parametrize(
    "line",
    ["README.md\tcontent\treviewed", "uv.lock\tsecret\treviewed", "uv.lock\thash\t"],
)
def test_scan_policy_rejects_broad_or_unjustified_exemptions(tmp_path: Path, line: str) -> None:
    """The optional allow file can never exempt an arbitrary public file or credential rule."""
    directory = create_policy(tmp_path)
    (directory / ("public-" + "scan-allow.txt")).write_text(line + "\n")
    with pytest.raises(ExportError):
        read_policy(directory)


def test_scan_policy_accepts_only_documented_lock_checksum_fields(tmp_path: Path) -> None:
    """Explicit lock checksum declarations remain equivalent to the scanner's narrow handling."""
    directory = create_policy(tmp_path)
    (directory / ("public-" + "scan-allow.txt")).write_text(
        "uv.lock\thash\tpackage checksum\nweb/package-lock.json\tintegrity\tpackage checksum\n"
    )
    assert read_policy(directory).excluded_patterns == ()


@pytest.mark.parametrize("pattern", ["../outside", "/absolute", "regex:anything", "*"])
def test_exclusion_policy_rejects_paths_that_escape_or_hide_everything(
    tmp_path: Path, pattern: str
) -> None:
    """Path policies stay repository-relative and cannot inject filter syntax."""
    directory = create_policy(tmp_path, exclusions=(pattern,))
    with pytest.raises(ExportError, match="Unsafe exclusion"):
        read_policy(directory)


@pytest.mark.parametrize(
    "changes",
    [
        {"deleted_empty_commit_count": 2},
        {"scanned_commits": 1},
        {"collapsed_commit_count": -1},
        {"success": True, "errors": ("failed",)},
    ],
)
def test_report_rejects_unreconciled_counts_or_incomplete_scan(changes: dict[str, object]) -> None:
    """A green report must account for every source commit and every retained scan target."""
    values: dict[str, object] = {
        "mode": "history",
        "source_ref": "main",
        "source_commit_count": 3,
        "deleted_empty_commit_count": 1,
        "retained_commit_count": 2,
        "scanned_commits": 2,
        **changes,
    }
    with pytest.raises(ValidationError):
        ExportReport.model_validate(values)


@pytest.mark.parametrize("finding", [False, True])
def test_cli_status_matches_saved_scanner_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, finding: bool
) -> None:
    """The command exits nonzero on scan findings while preserving exact file and line evidence."""
    source = create_source(tmp_path)
    policy_dir = create_policy(tmp_path)
    if finding:
        (source / "README.md").write_text("/" + "Users" + "/generated-person/private\n")
        commit(source, "docs: generated path fixture")
    monkeypatch.setattr(export_public, "filter_history", identity_filter)
    output = tmp_path / "output"
    monkeypatch.setattr(
        "sys.argv",
        [
            "export_public.py",
            "--source",
            str(source),
            "--out",
            str(output),
            "--policy-dir",
            str(policy_dir),
        ],
    )
    with pytest.raises(SystemExit) as stopped:
        export_public.main()
    assert stopped.value.code == int(finding)
    report = ExportReport.model_validate_json(
        (output / ".git" / export_public.REPORT_FILENAME).read_text()
    )
    assert bool(report.findings) is finding
    if finding:
        assert any(item.path == "README.md" and item.line == 1 for item in report.findings)


@pytest.mark.integration
@pytest.mark.parametrize("mode", ["history", "snapshot"])
def test_real_maintenance_tool_rewrites_history_and_preserves_dirty_source(
    tmp_path: Path, mode: str
) -> None:
    """Explicit integration runs use the temporary maintenance tool against generated local Git."""
    source = create_source(tmp_path, legacy_identity=True)
    policy_dir = create_policy(tmp_path, exclusions=("private/", "*.log"))
    (source / "private").mkdir()
    (source / "private/notes.md").write_text("Private generated notes.\n")
    (source / "logs/nested").mkdir(parents=True)
    (source / "logs/nested/build.log").write_text("Excluded generated log.\n")
    commit(source, "docs: private notes")
    (source / "README.md").write_text("The " + "Solar" + "Sense" + " architecture.\n")
    changed = commit(source, "docs: add " + "pro" + "mpt")
    (policy_dir / ("public-" + "replace.txt")).write_text(
        "literal:" + "Solar" + "Sense" + "==>neutral\n"
    )
    (policy_dir / ("public-" + "message-map.json")).write_text(
        json.dumps({changed: "docs: clarify public architecture"})
    )
    (source / "staged.txt").write_text("Staged local work.\n")
    git(source, "add", "staged.txt")
    (source / "README.md").write_text("Uncommitted local work.\n")
    before = source_state(source)
    output = tmp_path / "output"
    options = ExportOptions.model_validate(
        {"source": source, "out": output, "mode": mode, "policy_dir": policy_dir}
    )
    report = export_public.export_repository(options)
    assert report.success, report.model_dump_json()
    assert report.source_commit_count == 3
    assert report.deleted_empty_commit_count == 1
    assert report.retained_commit_count == (2 if mode == "history" else 1)
    assert report.collapsed_commit_count == (0 if mode == "history" else 1)
    assert source_state(source) == before
    assert (source / "staged.txt").read_text() == "Staged local work.\n"
    assert (output / "README.md").read_text() == "The neutral architecture.\n"
    assert not (output / "private").exists()
    assert not (output / "logs/nested/build.log").exists()
    assert not (output / "staged.txt").exists()
    assert not git(output, "log", "--all", "--", "private")
    assert set(git(output, "log", "--all", "--format=%an|%ae|%cn|%ce").splitlines()) == {
        f"{PUBLIC_NAME}|{PUBLIC_EMAIL}|{PUBLIC_NAME}|{PUBLIC_EMAIL}"
    }
    assert report.rewritten_messages[0].original_commit == changed
    assert report.rewritten_messages[0].filtered_commit


@pytest.mark.integration
def test_real_history_scan_finds_a_removed_sensitive_file(tmp_path: Path) -> None:
    """A clean final tree cannot conceal a sensitive path retained in earlier public history."""
    source = create_source(tmp_path)
    policy_dir = create_policy(tmp_path)
    (source / "old.txt").write_text("/" + "Users" + "/generated-person/private\n")
    offending = commit(source, "test: add generated path")
    (source / "old.txt").unlink()
    commit(source, "test: remove generated path")
    output = tmp_path / "output"
    report = export_public.export_repository(
        ExportOptions(source=source, out=output, policy_dir=policy_dir)
    )
    assert not report.success
    assert not report.errors
    assert not (output / "old.txt").exists()
    assert any(item.path == "old.txt" and item.line == 1 for item in report.findings)
    assert all(isinstance(item, ScanFinding) for item in report.findings)
    assert len(offending) == 40
