# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit the locked Python runtime closure, including recursively selected extras."""

from __future__ import annotations

import hashlib
import tomllib
from collections import deque
from importlib import metadata
from typing import TYPE_CHECKING

from packaging.markers import Marker
from packaging.utils import canonicalize_name

from datakeel.core.errors import ValidationError
from scripts.license_models import (
    LicenseFileEvidence,
    LicensePackage,
    LockedDependency,
    LockedPackage,
    ProjectManifest,
    PythonLock,
    SelectedPythonPackage,
)
from scripts.license_python_metadata import validate_requirements

if TYPE_CHECKING:
    from pathlib import Path

_LEGACY_EVIDENCE = (
    LicenseFileEvidence(
        name="python-dateutil",
        version="2.9.0.post0",
        declared="Dual License",
        filename="LICENSE",
        sha256="ba00f51a0d92823b5a1cde27d8b5b9d2321e67ed8da9bc163eff96d5e17e577e",
        license="BSD-3-Clause",
    ),
    LicenseFileEvidence(
        name="pyperclip",
        version="1.11.0",
        declared="BSD",
        filename="LICENSE.txt",
        sha256="a72b0acc9389e4c17ced890ef1b03455e04978d39e25636099b93efb76b74ead",
        license="BSD-3-Clause",
    ),
)
_ALIASES = {
    "Apache License 2.0": "Apache-2.0",
    "BSD 3-Clause License": "BSD-3-Clause",
    "MIT No Attribution": "MIT-0",
}
_CLASSIFIERS = {
    "License :: OSI Approved :: MIT License": "MIT",
}


def _selected_package(lock: PythonLock, dependency: LockedDependency) -> LockedPackage:
    candidates = [
        package
        for package in lock.packages
        if canonicalize_name(package.name) == canonicalize_name(dependency.name)
        and (dependency.version is None or package.version == dependency.version)
        and (
            not package.resolution_markers
            or any(Marker(marker).evaluate() for marker in package.resolution_markers)
        )
    ]
    if len(candidates) != 1:
        msg = f"Python lock dependency must resolve exactly once: {dependency.name}"
        raise ValidationError(msg)
    return candidates[0]


def _runtime_selection(lock: PythonLock, project_name: str) -> tuple[SelectedPythonPackage, ...]:
    pending = deque([LockedDependency(name=project_name)])
    visited: set[tuple[str, str, tuple[str, ...]]] = set()
    selected: dict[str, LockedPackage] = {}
    extras: dict[str, set[str]] = {}
    while pending:
        dependency = pending.popleft()
        if dependency.marker and not Marker(dependency.marker).evaluate():
            continue
        package = _selected_package(lock, dependency)
        identity = (package.name, package.version, tuple(sorted(dependency.extras)))
        if identity in visited:
            continue
        visited.add(identity)
        if package.name in selected and selected[package.name].version != package.version:
            msg = f"Python runtime resolves incompatible versions: {package.name}"
            raise ValidationError(msg)
        selected[package.name] = package
        extras.setdefault(package.name, set()).update(dependency.extras)
        pending.extend(package.dependencies)
        for extra in dependency.extras:
            if extra not in package.optional_dependencies:
                msg = f"Python lock is missing selected extra: {package.name}[{extra}]"
                raise ValidationError(msg)
            pending.extend(package.optional_dependencies[extra])
    return tuple(
        SelectedPythonPackage(package=package, extras=tuple(sorted(extras[name])))
        for name, package in sorted(selected.items())
    )


def runtime_closure(lock: PythonLock, project_name: str) -> tuple[LockedPackage, ...]:
    """Follow runtime edges and selected extras for the current Python/platform markers."""
    return tuple(
        item.package
        for item in _runtime_selection(lock, project_name)
        if canonicalize_name(item.package.name) != canonicalize_name(project_name)
    )


def _legacy_license(distribution: metadata.Distribution, declared: str) -> tuple[str, str] | None:
    name = canonicalize_name(distribution.metadata["Name"] or "")
    for reviewed in _LEGACY_EVIDENCE:
        if (name, distribution.version, declared) != (
            reviewed.name,
            reviewed.version,
            reviewed.declared,
        ):
            continue
        for file in distribution.files or ():
            if file.name == reviewed.filename and any(
                part.endswith(".dist-info") for part in file.parts
            ):
                actual = hashlib.sha256(file.read_binary()).hexdigest()
                if actual == reviewed.sha256:
                    return reviewed.license, f"reviewed {reviewed.filename} SHA-256 {actual}"
    return None


def declared_license(distribution: metadata.Distribution) -> tuple[str, str]:
    """Prefer SPDX metadata and never let classifiers override an explicit unknown license."""
    if expression := distribution.metadata.get("License-Expression"):
        return expression, "installed METADATA License-Expression"
    if declared := distribution.metadata.get("License"):
        if reviewed := _legacy_license(distribution, declared):
            return reviewed
        return _ALIASES.get(declared, declared), "installed METADATA License"
    classifiers = tuple(
        item
        for item in distribution.metadata.get_all("Classifier", ())
        if item.startswith("License ::")
    )
    if len(classifiers) == 1 and classifiers[0] in _CLASSIFIERS:
        return _CLASSIFIERS[classifiers[0]], "installed METADATA license classifier"
    return "UNKNOWN", "no unambiguous license in installed METADATA"


def python_packages(root: Path) -> tuple[LicensePackage, ...]:
    """Read locked runtime packages and require matching locally installed metadata."""
    lock = PythonLock.model_validate(tomllib.loads((root / "uv.lock").read_text()))
    project = ProjectManifest.model_validate(tomllib.loads((root / "pyproject.toml").read_text()))
    selection = _runtime_selection(lock, project.project.name)
    packages: list[LicensePackage] = []
    for item in selection:
        package = item.package
        if canonicalize_name(package.name) == canonicalize_name(project.project.name):
            validate_requirements(item, project.project.dependencies, selection)
            continue
        try:
            installed = metadata.distribution(package.name)
        except metadata.PackageNotFoundError as error:
            msg = f"Runtime package {package.name} is not installed; run uv sync --locked"
            raise ValidationError(msg) from error
        if (
            canonicalize_name(installed.metadata.get("Name", "")) != canonicalize_name(package.name)
            or installed.version != package.version
        ):
            msg = f"Installed identity differs from uv.lock: {package.name} {package.version}"
            raise ValidationError(msg)
        validate_requirements(item, tuple(installed.requires or ()), selection)
        license_id, evidence = declared_license(installed)
        packages.append(
            LicensePackage(
                ecosystem="python",
                name=package.name,
                version=package.version,
                license=license_id,
                evidence=evidence,
            )
        )
    return tuple(packages)
