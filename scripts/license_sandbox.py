# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit the fixed sandbox Python dependency layer against the main locked inventory."""

import re
from pathlib import Path

from scripts.license_models import LicensePackage

_EXPECTED_PACKAGES = {"numpy", "pillow"}


class SandboxLicenseError(ValueError):
    """Fail the normal license gate if the sandbox layer is not completely pinned."""


def sandbox_packages(
    root: Path, packages: tuple[LicensePackage, ...]
) -> tuple[LicensePackage, ...]:
    """Require the exact reviewed dependency layer and retain upstream evidence in notices."""
    dockerfile = root / "sandbox/Dockerfile"
    if not dockerfile.is_file():
        return ()
    lines = [line.strip() for line in dockerfile.read_text().splitlines() if line.strip()]
    bases = [line for line in lines if line.startswith("FROM ")]
    if len(bases) != 1 or not re.fullmatch(r"FROM python:[^ @]+@sha256:[0-9a-f]{64}", bases[0]):
        msg = "Sandbox base must be one official Python image pinned by sha256"
        raise SandboxLicenseError(msg)
    installs = [line for line in lines if line.startswith("RUN ")]
    if len(installs) != 1 or not installs[0].startswith(
        "RUN pip install --no-cache-dir --no-deps "
    ):
        msg = "Sandbox dependency layer must use one fixed, dependency-free pip installation"
        raise SandboxLicenseError(msg)
    specifications = installs[0].removeprefix("RUN pip install --no-cache-dir --no-deps ").split()
    selected: list[LicensePackage] = []
    inventory = {package.name.lower(): package for package in packages}
    for specification in specifications:
        match = re.fullmatch(r"(numpy|Pillow)==([0-9]+\.[0-9]+\.[0-9]+)", specification)
        if match is None:
            msg = "Sandbox contains an unreviewed or unpinned Python dependency"
            raise SandboxLicenseError(msg)
        name, version = match.groups()
        package = inventory.get(name.lower())
        if package is None or package.version != version:
            msg = "Sandbox dependency must match its audited main lock version"
            raise SandboxLicenseError(msg)
        selected.append(
            package.model_copy(
                update={
                    "ecosystem": "sandbox-python",
                    "evidence": "sandbox/Dockerfile; " + package.evidence,
                }
            )
        )
    if {package.name.lower() for package in selected} != _EXPECTED_PACKAGES or len(selected) != len(
        _EXPECTED_PACKAGES
    ):
        msg = "Sandbox dependency layer must contain exactly numpy and Pillow"
        raise SandboxLicenseError(msg)
    return tuple(selected)
