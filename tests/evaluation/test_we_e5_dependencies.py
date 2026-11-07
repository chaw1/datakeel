# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Actual-wheel inspection rejects runtime FAISS metadata and accidentally packaged dev code."""

import zipfile
from pathlib import Path

from scripts.we_e5.dependencies import inspect_wheel


def test_product_wheel_with_faiss_payload_is_rejected(tmp_path: Path) -> None:
    """A clean dependency list cannot hide a bundled FAISS payload."""
    wheel = tmp_path / "datakeel.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("faiss/__init__.py", "")
        archive.writestr("datakeel.dist-info/METADATA", "Name: datakeel\nVersion: 0.0.0\n")
    reason = None
    try:
        inspect_wheel(wheel)
    except ValueError as error:
        reason = str(error)
    assert reason == "development_code_in_product_wheel"


def test_product_wheel_with_faiss_requirement_is_rejected(tmp_path: Path) -> None:
    """A normal product wheel still fails when FAISS becomes a runtime requirement."""
    wheel = tmp_path / "datakeel.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "datakeel.dist-info/METADATA",
            "Name: datakeel\nVersion: 0.0.0\nRequires-Dist: faiss-cpu==1.15.1\n",
        )
    reason = None
    try:
        inspect_wheel(wheel)
    except ValueError as error:
        reason = str(error)
    assert reason == "faiss_in_wheel_runtime_dependencies"


def test_product_wheel_without_faiss_is_inspected(tmp_path: Path) -> None:
    """Ordinary runtime dependencies stay visible in the returned actual METADATA."""
    wheel = tmp_path / "datakeel.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            "datakeel.dist-info/METADATA",
            "Name: datakeel\nVersion: 0.0.0\nRequires-Dist: numpy>=2,<3\n",
        )
    message, count = inspect_wheel(wheel)
    assert message.get_all("Requires-Dist") == ["numpy>=2,<3"]
    assert count == 1
