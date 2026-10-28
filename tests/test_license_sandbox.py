# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Prevent the isolated image from bypassing the normal dependency license inventory."""

from pathlib import Path

import pytest

from scripts.license_models import LicensePackage
from scripts.license_sandbox import SandboxLicenseError, sandbox_packages

_BASE = "FROM python:3.12-slim-bookworm@sha256:" + "a" * 64
_INSTALL = "RUN pip install --no-cache-dir --no-deps numpy==2.5.4 Pillow==13.0.0"
_PACKAGES = (
    LicensePackage(
        ecosystem="python",
        name="numpy",
        version="2.5.4",
        license="BSD-3-Clause",
        evidence="locked fixture",
    ),
    LicensePackage(
        ecosystem="python",
        name="pillow",
        version="13.0.0",
        license="MIT-CMU",
        evidence="locked fixture",
    ),
)


def dockerfile(root: Path, content: str) -> None:
    """Write a generated image manifest without invoking a runtime."""
    sandbox = root / "sandbox"
    sandbox.mkdir()
    (sandbox / "Dockerfile").write_text(content)


def test_sandbox_dependencies_are_included_in_license_notices(tmp_path: Path) -> None:
    """Every pinned Python dependency retains its existing verified SPDX evidence."""
    dockerfile(tmp_path, _BASE + "\n" + _INSTALL)
    inventory = sandbox_packages(tmp_path, _PACKAGES)
    assert [package.ecosystem for package in inventory] == ["sandbox-python", "sandbox-python"]
    assert {package.license for package in inventory} == {"BSD-3-Clause", "MIT-CMU"}
    assert all("sandbox/Dockerfile" in package.evidence for package in inventory)


@pytest.mark.parametrize(
    "content",
    [
        "FROM python:3.12-slim\n" + _INSTALL,
        _BASE + "\nRUN pip install numpy pillow",
        _BASE + "\n" + _INSTALL + "\nRUN pip install unknown",
        _BASE + "\n" + _INSTALL.replace("2.5.4", "2.5.3"),
        _BASE + "\n" + _INSTALL + " requests==2.0.0",
        _BASE + "\n" + _INSTALL.replace(" Pillow==13.0.0", ""),
    ],
)
def test_sandbox_unreviewed_dependency_layers_fail_audit(tmp_path: Path, content: str) -> None:
    """Changing pins, the base, or installation commands cannot silently escape the gate."""
    dockerfile(tmp_path, content)
    with pytest.raises(SandboxLicenseError):
        sandbox_packages(tmp_path, _PACKAGES)
