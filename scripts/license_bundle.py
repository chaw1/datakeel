# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate measured build dependency evidence against the current frontend source bytes."""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from datakeel.core.errors import ValidationError
from scripts.license_models import BundleInventory

if TYPE_CHECKING:
    from pathlib import Path


def source_hash(web: Path) -> str:
    """Match the existing frontend sourceHash algorithm, including paths and byte lengths."""
    entries = list((web / "src").rglob("*"))
    if any(path.is_symlink() for path in entries):
        msg = "Frontend source entries cannot be symbolic links"
        raise ValidationError(msg)
    paths = [path.relative_to(web).as_posix() for path in entries if path.is_file()]
    paths.append("package-lock.json")
    digest = hashlib.sha256()
    for relative in sorted(paths, key=lambda item: item.encode("utf-16-be")):
        contents = (web / relative).read_bytes()
        digest.update(f"{relative}\0{len(contents)}\0".encode())
        digest.update(contents)
        digest.update(b"\0")
    return digest.hexdigest()


def bundle_packages(root: Path) -> tuple[str, ...]:
    """Require current build evidence and safe package locations before auditing its closure."""
    path = root / "datakeel" / "web_dist" / ".runtime-dependencies.json"
    if not path.is_file():
        msg = "Frontend bundle inventory is missing; run npm run build"
        raise ValidationError(msg)
    inventory = BundleInventory.model_validate_json(path.read_text())
    if inventory.source_hash != source_hash(root / "web"):
        msg = "Frontend bundle inventory is stale; run npm run build"
        raise ValidationError(msg)
    if inventory.packages != tuple(sorted(set(inventory.packages))):
        msg = "Frontend bundle inventory package locations must be sorted and unique"
        raise ValidationError(msg)
    for location in inventory.packages:
        if (
            not location.startswith("node_modules/")
            or any(part in {"", ".", ".."} for part in location.split("/"))
            or PurePosixPath(location).is_absolute()
        ):
            msg = "Frontend bundle inventory contains an invalid package location"
            raise ValidationError(msg)
    return inventory.packages
