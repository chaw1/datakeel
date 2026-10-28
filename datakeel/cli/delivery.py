# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Database-free recipient verification and local release command grammar."""

import argparse
import json
import tarfile
from pathlib import Path

from pydantic import ValidationError as ModelValidationError
from rich.console import Console

from datakeel.cli.parsers import CommandGroup
from datakeel.core.delivery_models import ReconcileReport
from datakeel.core.errors import DatakeelError
from datakeel.delivery.reconcile import reconcile, report_json
from datakeel.storage.database import Database
from datakeel.storage.delivery_service import export_release, reconcile_release
from datakeel.storage.version_diff import compare_versions

_LABELS = {
    "file_count": "文件数 / File count",
    "bytes": "字节数 / Bytes",
    "hashes": "内容哈希 / Content hashes",
    "annotations": "标注与标签 / Annotations and labels",
    "metadata": "元数据 / Metadata",
    "lineage": "血缘引用 / Lineage",
}


def register_parser(commands: CommandGroup) -> None:
    """Add recipient reconciliation and paginated version comparison commands."""
    offline = commands.add_parser("reconcile")
    offline.add_argument("source", type=Path)
    offline.add_argument("--manifest", type=Path, default=Path("MANIFEST.json"))
    offline.add_argument("--json", action="store_true", dest="json_output")
    compare = commands.add_parser("version-diff")
    compare.add_argument("dataset")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--offset", type=int, default=0)
    compare.add_argument("--limit", type=int, default=100)
    compare.add_argument(
        "--category",
        choices=["added", "removed", "content_changed", "metadata_changed", "unchanged"],
    )
    compare.add_argument("--json", action="store_true", dest="json_output")
    export = commands.add_parser("release-export")
    export.add_argument("release")
    export.add_argument("--output", required=True, type=Path)
    check = commands.add_parser("release-reconcile")
    check.add_argument("release")
    check.add_argument("--json", action="store_true", dest="json_output")


def offline_command(args: argparse.Namespace) -> None:
    """Run before settings, routing configuration or database initialization."""
    try:
        report = reconcile(args.source, args.manifest)
    except (DatakeelError, ModelValidationError, OSError, tarfile.TarError) as error:
        reason = type(error).__name__
        message = (
            json.dumps({"error": "invalid_delivery", "reason": reason})
            if args.json_output
            else f"无法读取交付包 / Invalid delivery: {reason}"
        )
        Console().print(message, markup=False, highlight=False)
        raise SystemExit(2) from None
    render_report(report, json_output=args.json_output)
    if not report.passed:
        raise SystemExit(1)


def render_report(report: ReconcileReport, *, json_output: bool = False) -> None:
    """Render a bilingual summary or a machine-readable six-category receipt."""
    console = Console()
    if json_output:
        console.print(report_json(report), markup=False, highlight=False, soft_wrap=True)
        return
    for category in report.categories:
        status = "通过 / PASS" if category.passed else "失败 / FAIL"
        console.print(f"{_LABELS[category.name]}: {status}", markup=False)
        for item in category.differences:
            console.print(
                f"  {item.path}: {item.reason}; expected={item.expected!r}; actual={item.actual!r}",
                markup=False,
            )


def database_command(db: Database, args: argparse.Namespace) -> None:
    """Read paginated comparisons or export and verify one frozen publication."""
    if args.command == "version-diff":
        comparison = compare_versions(
            db, args.dataset, args.before, args.after, (args.offset, args.limit), args.category
        )
        payload = comparison.model_dump(mode="json")
        Console().print(
            json.dumps(payload, ensure_ascii=False, indent=2),
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
    elif args.command == "release-export":
        path = export_release(db, args.release, args.output)
        Console().print(str(path), markup=False)
    else:
        report = reconcile_release(db, args.release)
        render_report(report, json_output=args.json_output)
        if not report.passed:
            raise SystemExit(1)
