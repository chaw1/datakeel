# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Export a scanned public history or snapshot into a new local directory."""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from rich.console import Console

from scripts.public_export_git import (
    clone_selected,
    collapse_snapshot,
    filter_history,
    git,
    message_rewrites,
)
from scripts.public_export_models import ExportError, ExportOptions, ExportReport
from scripts.public_export_policy import read_policy
from scripts.public_scan import scan_repository

REPORT_FILENAME = "public-export-report.json"


def _validate_destination(source: Path, destination: Path) -> None:
    git_directory = Path(git(source, "rev-parse", "--absolute-git-dir")).resolve()
    common_directory = Path(git(source, "rev-parse", "--git-common-dir"))
    common_directory = (source / common_directory).resolve()
    if (
        source.is_relative_to(destination)
        or destination.is_relative_to(git_directory)
        or destination.is_relative_to(common_directory)
    ):
        msg = "The export destination cannot contain the source or use Git metadata storage"
        raise ExportError(msg)
    if destination.is_relative_to(source):
        relative = destination.relative_to(source).as_posix()
        try:
            git(source, "check-ignore", "--no-index", "--", relative + "/")
        except ExportError as error:
            msg = "An export inside the source must use a Git-ignored new directory"
            raise ExportError(msg) from error
        if git(source, "ls-files", "--", relative):
            msg = "The export destination overlaps tracked source files"
            raise ExportError(msg)


def _reserve_destination(options: ExportOptions) -> tuple[Path, Path]:
    source = options.source.resolve(strict=True)
    destination = options.out.absolute()
    if destination.exists() or destination.is_symlink():
        msg = "The export destination already exists; choose a new directory"
        raise ExportError(msg)
    resolved = destination.resolve()
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        msg = "The source must name the local repository root"
        raise ExportError(msg)
    _validate_destination(source, resolved)
    if git(source, "rev-parse", "--is-shallow-repository") != "false":
        msg = "A complete local source history is required"
        raise ExportError(msg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    return source, destination


def _build_export(options: ExportOptions, source: Path, repository: Path) -> ExportReport:
    policy = read_policy(options.policy_dir or source / "scripts")
    commit = git(source, "rev-parse", "--verify", "--end-of-options", f"{options.ref}^{{commit}}")
    source_count = int(git(source, "rev-list", "--count", commit))
    clone_selected(source, repository, commit)
    filter_history(repository, policy, repository.parent)
    filtered_count = int(git(repository, "rev-list", "--count", "--all"))
    if filtered_count == 0:
        msg = "No public commits remain after filtering"
        raise ExportError(msg)
    rewrites = message_rewrites(repository, policy)
    if options.mode == "snapshot":
        collapse_snapshot(repository)
    retained_count = int(git(repository, "rev-list", "--count", "--all"))
    scan = scan_repository(repository, policy.excluded_patterns)
    return ExportReport(
        mode=options.mode,
        source_ref=options.ref,
        source_commit=commit,
        source_commit_count=source_count,
        deleted_empty_commit_count=source_count - filtered_count,
        retained_commit_count=retained_count,
        collapsed_commit_count=max(0, filtered_count - retained_count),
        rewritten_messages=rewrites,
        findings=scan.findings,
        images=scan.images,
        scanned_commits=scan.scanned_commits,
        success=not scan.findings,
    )


def export_repository(options: ExportOptions) -> ExportReport:
    """Preserve the source and retain a reviewable destination even when the scan fails."""
    source, destination = _reserve_destination(options)
    with TemporaryDirectory(prefix="datakeel-public-") as directory:
        repository = Path(directory) / "repository"
        try:
            report = _build_export(options, source, repository)
        except (ExportError, OSError, ValueError, subprocess.SubprocessError) as error:
            report = ExportReport(mode=options.mode, source_ref=options.ref, errors=(str(error),))
        if repository.is_dir():
            shutil.copytree(repository, destination, dirs_exist_ok=True, symlinks=True)
        metadata = destination / ".git"
        metadata.mkdir(exist_ok=True)
        (metadata / REPORT_FILENAME).write_text(report.model_dump_json(indent=2) + "\n")
    return report


def main() -> None:
    """Exit successfully only after all reachable exported commits pass the public scanner."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--mode", choices=("history", "snapshot"), default="history")
    parser.add_argument("--ref", default="main")
    parser.add_argument("--policy-dir", type=Path)
    options = ExportOptions.model_validate(vars(parser.parse_args()))
    console = Console()
    try:
        report = export_repository(options)
    except (ExportError, OSError) as error:
        console.print(str(error), markup=False)
        raise SystemExit(1) from error
    console.print(f"Report: {options.out / '.git' / REPORT_FILENAME}", markup=False)
    console.print(
        f"Retained commits: {report.retained_commit_count}; findings: {len(report.findings)}; "
        f"errors: {len(report.errors)}"
    )
    raise SystemExit(0 if report.success else 1)


if __name__ == "__main__":
    main()
