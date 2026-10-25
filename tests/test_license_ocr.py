# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep optional OCR exceptions isolated and reject concealed native video dependencies."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import license_ocr_evidence, license_ocr_native, license_python
from scripts.license_audit import license_findings
from scripts.license_models import LicensePackage
from scripts.license_ocr import ocr_license_findings
from tests.test_license_python import distribution


def _package(name: str, license_id: str, version: str = "1.0") -> LicensePackage:
    return LicensePackage(
        ecosystem="python", name=name, version=version, license=license_id, evidence="fixture"
    )


def test_optional_exception_when_tqdm_is_selected_does_not_change_core_policy() -> None:
    """The approved compound license is confined to exact optional package identity."""
    package = _package("tqdm", "MPL-2.0 AND MIT")
    assert ocr_license_findings(package) == ()
    assert license_findings(package)
    assert ocr_license_findings(_package("other", package.license))
    assert ocr_license_findings(_package("tqdm", "MPL-2.0"))
    assert ocr_license_findings(_package("tqdm", "invalid declaration"))


def test_optional_audit_when_runtime_metadata_omits_bundled_eigen_still_rejects() -> None:
    """The CPU wheel's verified Eigen code needs a separate policy decision from tqdm."""
    package = _package("onnxruntime", "MIT", "1.31.0")
    finding = ocr_license_findings(package)
    assert len(finding) == 1
    assert finding[0].license == "MIT AND MPL-2.0"
    assert "Eigen" in finding[0].reason
    assert license_findings(package) == ()


def test_python_inventory_when_project_extra_explicitly_selected_includes_only_its_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unselected extras stay out of the unchanged default core inventory."""
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="application"\ndependencies=[]\n[project.optional-dependencies]\nocr=["generated>=1"]\n'
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="application"\nversion="1.0"\n[package.optional-dependencies]\nocr=[{name="generated"}]\n[[package]]\nname="generated"\nversion="1.0"\n'
    )
    installed = distribution(tmp_path, "License-Expression: MIT\n")
    monkeypatch.setattr(license_python.metadata, "distribution", lambda _: installed)
    assert license_python.python_packages(tmp_path) == ()
    assert [
        package.name for package in license_python.python_packages(tmp_path, extras=("ocr",))
    ] == ["generated"]


def test_reviewed_optional_metadata_when_any_evidence_changes_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An alias cannot survive changed version, declaration or license-file bytes."""
    installed = distribution(tmp_path, "License: ambiguous\n")
    expected = hashlib.sha256(b"Generated license terms").hexdigest()
    reviewed = SimpleNamespace(
        name="generated",
        version="1.0",
        declared="ambiguous",
        license="MIT",
        files={"LICENSE": expected},
    )
    monkeypatch.setattr(license_ocr_evidence, "_REVIEWED", (reviewed,))
    monkeypatch.setattr(license_ocr_evidence.metadata, "distribution", lambda _: installed)
    package = _package("generated", "ambiguous")
    assert license_ocr_evidence.reviewed_ocr_license(package).license == "MIT"
    changed = package.model_copy(update={"version": "2.0"})
    assert license_ocr_evidence.reviewed_ocr_license(changed) == changed
    (tmp_path / "generated-1.0.dist-info" / "LICENSE").write_text("Changed license terms")
    assert license_ocr_evidence.reviewed_ocr_license(package) == package


@pytest.mark.parametrize(
    ("files", "build", "rejected"),
    [
        (("cv2/.dylibs/libavcodec.61.dylib",), "FFMPEG: NO", True),
        (("cv2/.libs/libavcodec.so.61",), "FFMPEG: NO", True),
        (("cv2/cv2.abi3.so",), "GStreamer: YES", True),
        (("cv2/cv2.abi3.so",), "FFMPEG: YES", True),
        (("cv2/cv2.abi3.so",), "FFMPEG: NO", False),
    ],
)
def test_native_audit_when_video_binary_or_enabled_backend_is_present_fails(
    monkeypatch: pytest.MonkeyPatch, files: tuple[str, ...], build: str, *, rejected: bool
) -> None:
    """Package-level Apache metadata cannot hide bundled copyleft video libraries."""
    monkeypatch.setattr(
        license_ocr_native.metadata,
        "distribution",
        lambda _: SimpleNamespace(version="fixture", files=tuple(Path(name) for name in files)),
    )
    monkeypatch.setattr(
        license_ocr_native,
        "import_module",
        lambda _: SimpleNamespace(getBuildInformation=lambda: build),
    )
    assert bool(license_ocr_native.native_findings()) == rejected
