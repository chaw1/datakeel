# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve npm production dependency trees, including nested packages and runtime peers."""

from __future__ import annotations

from collections import deque
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from datakeel.core.errors import ValidationError
from scripts.license_bundle import bundle_packages
from scripts.license_models import FrontendLock, FrontendPackage, LicensePackage

if TYPE_CHECKING:
    from pathlib import Path

_RUNTIME_FIELDS = {"dependencies", "optional_dependencies", "peer_dependencies", "peer_metadata"}


def _resolve_dependency(lock: FrontendLock, parent: str, name: str) -> str | None:
    path = PurePosixPath(parent)
    for directory in (path, *path.parents):
        candidate = str(directory / "node_modules" / name)
        if candidate in lock.packages:
            return candidate
    return None


def _dependencies(package: FrontendPackage) -> tuple[tuple[str, bool], ...]:
    required = {**package.dependencies, **package.peer_dependencies}
    optional = set(package.optional_dependencies)
    optional.update(
        name
        for name, meta in package.peer_metadata.items()
        if meta.optional and name not in package.dependencies
    )
    return tuple((name, name in optional) for name in sorted(required.keys() | optional))


def production_closure(
    lock: FrontendLock, installed: frozenset[str] | None = None
) -> tuple[str, ...]:
    """Follow production roots rather than including build and development tools."""
    if "" not in lock.packages:
        msg = "npm lock is missing its root package"
        raise ValidationError(msg)
    pending = deque([""])
    selected: set[str] = set()
    while pending:
        location = pending.popleft()
        if location in selected:
            continue
        selected.add(location)
        for name, optional in _dependencies(lock.packages[location]):
            dependency = _resolve_dependency(lock, location, name)
            if dependency is None and not optional:
                msg = f"npm lock is missing required runtime dependency: {name}"
                raise ValidationError(msg)
            if dependency is not None and (
                not optional or installed is None or dependency in installed
            ):
                pending.append(dependency)
    return tuple(sorted(selected - {""}))


def _matching_metadata(locked: FrontendPackage, installed: FrontendPackage, location: str) -> bool:
    expected_name = locked.name or location.rsplit("node_modules/", 1)[-1]
    return (
        expected_name == installed.name
        and locked.version == installed.version
        and locked.license == installed.license
        and locked.model_dump(include=_RUNTIME_FIELDS)
        == installed.model_dump(include=_RUNTIME_FIELDS)
    )


def _runtime_locations(directory: Path, lock: FrontendLock) -> tuple[str, ...]:
    installed = frozenset(
        location for location in lock.packages if (directory / location / "package.json").is_file()
    )
    locations = set(production_closure(lock, installed))
    measured = bundle_packages(directory.parent)
    if any(location not in lock.packages for location in measured):
        msg = "Bundled frontend package is absent from the lock"
        raise ValidationError(msg)
    locations.update(measured)
    return tuple(sorted(locations))


def frontend_packages(root: Path) -> tuple[LicensePackage, ...]:
    """Check exact installed production versions and both manifest and lock license metadata."""
    directory = root / "web"
    lock = FrontendLock.model_validate_json((directory / "package-lock.json").read_text())
    manifest = FrontendPackage.model_validate_json((directory / "package.json").read_text())
    locked_root = lock.packages.get("", FrontendPackage())
    if manifest.model_dump(include=_RUNTIME_FIELDS) != locked_root.model_dump(
        include=_RUNTIME_FIELDS
    ):
        msg = "Frontend runtime dependencies differ from package-lock.json; run npm ci"
        raise ValidationError(msg)
    result: list[LicensePackage] = []
    for location in _runtime_locations(directory, lock):
        package = lock.packages[location]
        path = directory / location / "package.json"
        if not path.is_file():
            msg = f"Frontend runtime package is not installed: {location}; run npm ci"
            raise ValidationError(msg)
        installed = FrontendPackage.model_validate_json(path.read_text())
        if not _matching_metadata(package, installed, location):
            msg = f"Installed frontend metadata differs from lock: {location}"
            raise ValidationError(msg)
        result.append(
            LicensePackage(
                ecosystem="frontend",
                name=installed.name,
                version=installed.version,
                license=installed.license or "UNKNOWN",
                evidence=f"package-lock.json and {location}/package.json",
            )
        )
    return tuple(result)
