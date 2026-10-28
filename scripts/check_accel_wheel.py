# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Apply the existing public-content rules to every text member of an accelerator wheel."""

from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZipFile

from rich.console import Console

from datakeel.core.models import BoundaryModel
from scripts.public_scan import MAX_BLOB_BYTES
from scripts.public_scan_rules import text_findings


class WheelFinding(BoundaryModel):
    """Locate a prohibited pattern without retaining or printing the matched value."""

    member: str
    line: int
    rule: str


class WheelInspection(BoundaryModel):
    """Report artifact-level content checks without disclosing a local wheel path."""

    wheel: str
    members: int
    text_members: int
    findings: tuple[WheelFinding, ...]


def _binary_findings(member: str, data: bytes) -> tuple[WheelFinding, ...]:
    return tuple(
        WheelFinding(member=member, line=finding.line, rule=finding.rule)
        for finding in text_findings(member, data.decode("latin-1"), ())
        if finding.rule == "local_path"
    )


def inspect_wheel(path: Path) -> WheelInspection:
    """Scan text with worktree rules and reject native binaries containing local source paths."""
    findings: list[WheelFinding] = []
    text_members = 0
    with ZipFile(path) as archive:
        members = archive.infolist()
        for member in members:
            data = archive.read(member)
            try:
                source = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                findings.extend(_binary_findings(member.filename, data))
                continue
            if "\0" in source:
                findings.extend(_binary_findings(member.filename, data))
                continue
            text_members += 1
            if len(data) > MAX_BLOB_BYTES:
                findings.append(WheelFinding(member=member.filename, line=1, rule="oversized_blob"))
            findings.extend(
                WheelFinding(member=member.filename, line=finding.line, rule=finding.rule)
                for finding in text_findings(member.filename, source, ())
            )
    return WheelInspection(
        wheel=path.name,
        members=len(members),
        text_members=text_members,
        findings=tuple(findings),
    )


def main() -> None:
    """Fail the build when any wheel text contains a prohibited public-content pattern."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheels", type=Path, nargs="+")
    parser.add_argument("--json-report", type=Path)
    args = parser.parse_args()
    console = Console()
    reports = tuple(inspect_wheel(path) for path in args.wheels)
    if args.json_report:
        args.json_report.write_text(
            "[\n" + ",\n".join(report.model_dump_json(indent=2) for report in reports) + "\n]\n"
        )
    for report in reports:
        for finding in report.findings:
            console.print(
                f"{report.wheel}:{finding.member}:{finding.line}: {finding.rule}", markup=False
            )
        console.print(
            f"Wheel {report.wheel}: {report.text_members} text members, "
            f"{len(report.findings)} findings."
        )
    raise SystemExit(any(report.findings for report in reports))


if __name__ == "__main__":
    main()
