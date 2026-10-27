# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate the official base distribution inventory without expanding Python license policy."""

import re
from pathlib import Path

from scripts.license_base_models import BaseImageInventory
from scripts.license_models import LicensePackage


def validate_base_inventory(root: Path, packages: tuple[LicensePackage, ...]) -> BaseImageInventory:
    """Bind the inventory to the Dockerfile pin and existing audited Python package versions."""
    dockerfile = (root / "sandbox/Dockerfile").read_text()
    references = re.findall(r"^FROM (.+)$", dockerfile, re.MULTILINE)
    inventory = BaseImageInventory.model_validate_json(
        (root / "sandbox/BASE_IMAGE_INVENTORY.json").read_text()
    )
    if references != [inventory.base_reference]:
        msg = "Base license inventory must be regenerated when the Dockerfile base changes"
        raise ValueError(msg)
    installed = {package.name.lower(): package for package in inventory.python_packages}
    audited = {package.name.lower(): package for package in packages}
    for name in ("numpy", "pillow"):
        if (
            name not in installed
            or name not in audited
            or installed[name].version != audited[name].version
        ):
            msg = "Base inventory Python layer must match the audited sandbox dependency versions"
            raise ValueError(msg)
    return inventory


def base_python_packages(inventory: BaseImageInventory) -> tuple[LicensePackage, ...]:
    """Apply the existing Python license policy to actual interpreter and installed wheel terms."""
    runtime = LicensePackage(
        ecosystem="sandbox-python",
        name="cpython",
        version=inventory.python.version,
        license=inventory.python.license,
        evidence="sandbox/BASE_IMAGE_INVENTORY.json; " + inventory.python.evidence.path,
    )
    wheels = tuple(
        LicensePackage(
            ecosystem="sandbox-python",
            name=package.name.lower(),
            version=package.version,
            license=package.license,
            evidence="sandbox/BASE_IMAGE_INVENTORY.json; " + package.evidence[0].path,
        )
        for package in inventory.python_packages
    )
    return (runtime, *wheels)
