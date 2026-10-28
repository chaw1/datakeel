# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind the separately licensed official base inventory to its actual pinned image layer."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.license_audit import license_findings
from scripts.license_base import base_python_packages, validate_base_inventory
from scripts.license_base_models import BaseImageInventory
from scripts.license_models import LicensePackage

_ROOT = Path(__file__).resolve().parents[1]
_PACKAGES = (
    LicensePackage(
        ecosystem="python",
        name="numpy",
        version="2.5.4",
        license="BSD-3-Clause",
        evidence="fixture",
    ),
    LicensePackage(
        ecosystem="python", name="pillow", version="13.0.0", license="MIT-CMU", evidence="fixture"
    ),
)


def test_base_inventory_has_actual_runtime_and_all_os_notices() -> None:
    """Every recorded system package and wheel has retained, hashed upstream copyright files."""
    inventory = validate_base_inventory(_ROOT, _PACKAGES)
    assert inventory.os_package_count == len(inventory.os_packages)
    assert all(package.copyright.sha256 and package.licenses for package in inventory.os_packages)
    assert all(package.evidence for package in inventory.python_packages)
    packages = base_python_packages(inventory)
    assert {package.name for package in packages} >= {"cpython", "pip", "numpy", "pillow"}
    assert not any(license_findings(package) for package in packages)


def test_base_inventory_pin_change_requires_regeneration(tmp_path: Path) -> None:
    """Changing the Dockerfile base invalidates its retained dependency evidence."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    (sandbox / "BASE_IMAGE_INVENTORY.json").write_text(
        (_ROOT / "sandbox/BASE_IMAGE_INVENTORY.json").read_text()
    )
    (sandbox / "Dockerfile").write_text("FROM python:3.12-slim@sha256:" + "b" * 64)
    with pytest.raises(ValueError, match="regenerated"):
        validate_base_inventory(tmp_path, _PACKAGES)


@pytest.mark.parametrize(
    "mutation", ["missing_sha", "missing_notice", "missing_license", "missing_package"]
)
def test_base_inventory_missing_package_evidence_fails(mutation: str) -> None:
    """Removing a package or any required copyright/license evidence fails the normal gate."""
    inventory = json.loads((_ROOT / "sandbox/BASE_IMAGE_INVENTORY.json").read_text())
    first = inventory["os_packages"][0]
    if mutation == "missing_sha":
        first["copyright"]["sha256"] = ""
    elif mutation == "missing_notice":
        first.pop("copyright")
    elif mutation == "missing_license":
        first["licenses"] = []
    else:
        inventory["os_packages"].pop()
    with pytest.raises(ValidationError):
        BaseImageInventory.model_validate(inventory)
