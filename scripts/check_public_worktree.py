# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fail the quality gate when publishable worktree files contain private material."""

from pathlib import Path

from rich.console import Console

from scripts.public_scan import scan_worktree


def main() -> None:
    """Print relative file/line/rule findings without revealing matched values."""
    report = scan_worktree(Path.cwd())
    console = Console()
    for finding in report.findings:
        console.print(f"{finding.path}:{finding.line}: {finding.rule}", markup=False)
    console.print(
        f"Public worktree scan: {report.scanned_blobs} files, {len(report.findings)} findings."
    )
    raise SystemExit(bool(report.findings))


if __name__ == "__main__":
    main()
