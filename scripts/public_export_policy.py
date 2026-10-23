# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read strict private rewrite policies without broadening public scan exemptions."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from pydantic import TypeAdapter

from scripts.public_export_models import ExportError, ExportPolicy

if TYPE_CHECKING:
    from pathlib import Path

_PREFIX = "public-"
_ALLOW_COLUMNS = 3


def _lines(path: Path) -> tuple[str, ...]:
    return tuple(
        line.strip()
        for line in path.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )


def _validate_exclusions(patterns: tuple[str, ...]) -> None:
    for pattern in patterns:
        path = PurePosixPath(pattern)
        if (
            path.is_absolute()
            or ".." in path.parts
            or ":" in pattern
            or "\\" in pattern
            or pattern in {".", "*", "**", "/"}
        ):
            msg = f"Unsafe exclusion pattern: {pattern}"
            raise ExportError(msg)


def _validate_scan_allow(path: Path) -> None:
    for line in _lines(path):
        fields = line.split("\t")
        if len(fields) != _ALLOW_COLUMNS or not fields[2].strip():
            msg = "Scan exemptions require a path, lock field, and reason separated by tabs"
            raise ExportError(msg)
        name, field, _reason = fields
        permitted = (name == "uv.lock" and field == "hash") or (
            PurePosixPath(name).name == "package-lock.json"
            and not PurePosixPath(name).is_absolute()
            and ".." not in PurePosixPath(name).parts
            and field == "integrity"
        )
        if not permitted:
            msg = "Only lock-file checksum fields may be listed as scan exemptions"
            raise ExportError(msg)


def read_policy(directory: Path) -> ExportPolicy:
    """Read all four policy files and reject arbitrary exemptions or executable path rules."""
    patterns = _lines(directory / f"{_PREFIX}exclude.txt")
    _validate_exclusions(patterns)
    _validate_scan_allow(directory / f"{_PREFIX}scan-allow.txt")
    messages = TypeAdapter(dict[str, str]).validate_json(
        (directory / f"{_PREFIX}message-map.json").read_text(), strict=True
    )
    if any(
        re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", sha) is None or not message.strip()
        for sha, message in messages.items()
    ):
        msg = "Message rewrites require full original commit IDs and nonempty replacement messages"
        raise ExportError(msg)
    return ExportPolicy(
        excluded_patterns=patterns,
        replacements=(directory / f"{_PREFIX}replace.txt").read_text(),
        messages=messages,
    )
