# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate installed Python runtime dependency edges against the resolved lock graph."""

from __future__ import annotations

from typing import TYPE_CHECKING

from packaging.markers import Marker
from packaging.requirements import InvalidRequirement, Requirement
from packaging.utils import canonicalize_name

from datakeel.core.errors import ValidationError

if TYPE_CHECKING:
    from scripts.license_models import SelectedPythonPackage


def _active(marker: Marker | None, extras: tuple[str, ...]) -> bool:
    return marker is None or any(marker.evaluate({"extra": extra}) for extra in ("", *extras))


def _locked_edges(selected: SelectedPythonPackage) -> dict[str, set[str]]:
    package = selected.package
    dependencies = [*package.dependencies]
    for extra in selected.extras:
        dependencies.extend(package.optional_dependencies[extra])
    edges: dict[str, set[str]] = {}
    for dependency in dependencies:
        marker = Marker(dependency.marker) if dependency.marker else None
        if _active(marker, selected.extras):
            edges.setdefault(canonicalize_name(dependency.name), set()).update(
                canonicalize_name(extra) for extra in dependency.extras
            )
    return edges


def _parse_requirements(requirements: tuple[str, ...]) -> tuple[Requirement, ...]:
    try:
        return tuple(Requirement(value) for value in requirements)
    except InvalidRequirement as error:
        msg = f"Invalid runtime requirement: {error}"
        raise ValidationError(msg) from error


def validate_requirements(
    selected: SelectedPythonPackage,
    requirements: tuple[str, ...],
    packages: tuple[SelectedPythonPackage, ...],
) -> None:
    """Require matching active names/extras and versions satisfying every installed constraint."""
    versions = {canonicalize_name(item.package.name): item.package.version for item in packages}
    actual: dict[str, set[str]] = {}
    for requirement in _parse_requirements(requirements):
        if not _active(requirement.marker, selected.extras):
            continue
        name = canonicalize_name(requirement.name)
        version = versions.get(name)
        if (
            requirement.url
            or version is None
            or not requirement.specifier.contains(version, prereleases=True)
        ):
            msg = (
                f"Runtime requirement differs from uv.lock: "
                f"{selected.package.name} requires {requirement}"
            )
            raise ValidationError(msg)
        actual.setdefault(name, set()).update(
            canonicalize_name(extra) for extra in requirement.extras
        )
    if actual != _locked_edges(selected):
        msg = f"Runtime dependencies differ from uv.lock: {selected.package.name}"
        raise ValidationError(msg)
