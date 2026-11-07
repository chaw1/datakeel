# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline development-closure notices, installed integrity and product-wheel exclusion evidence."""

from __future__ import annotations

import argparse
import base64
import hashlib
import tomllib
import zipfile
from email.parser import BytesParser
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

from datakeel.core.models import BoundaryModel
from scripts.license_audit import license_findings
from scripts.license_models import (
    LicensePackage,
    LockedArtifact,
    LockedPackage,
    ProjectManifest,
    PythonLock,
    SelectedPythonPackage,
)
from scripts.license_python import declared_license, runtime_closure
from scripts.license_python_metadata import validate_requirements

if TYPE_CHECKING:
    from email.message import Message


class RetainedFile(BoundaryModel):
    """Record a retained license/notice or installed native object's actual content hash."""

    filename: str
    sha256: str
    size: int


class DevelopmentPackage(BoundaryModel):
    """Bind complete installed development metadata to locked identity and upstream pins."""

    package: LicensePackage
    requirements: tuple[str, ...]
    wheels: tuple[LockedArtifact, ...]
    notices: tuple[RetainedFile, ...]
    native_files: tuple[RetainedFile, ...]
    record_hashes_verified: int


class DependencyReport(BoundaryModel):
    """Separate the new development closure from the unchanged runtime dependency inventory."""

    development: tuple[DevelopmentPackage, ...]
    runtime_names: tuple[str, ...]
    wheel_filename: str
    wheel_sha256: str
    wheel_requires_dist: tuple[str, ...]
    wheel_members: int
    findings: tuple[str, ...] = ()
    source_imports_faiss: bool = False
    faiss_in_product_wheel: bool = False
    full_runtime_license_audit: str = "separate_existing_license_audit_required"
    native_notice_scope: str = (
        "approved_exact_development_distribution_only; retain upstream native notices; "
        "not_a_new_runtime_or_Rust_license_exception"
    )


def _file_evidence(filename: str, content: bytes) -> RetainedFile:
    return RetainedFile(
        filename=filename, sha256=hashlib.sha256(content).hexdigest(), size=len(content)
    )


def _installed(package: LockedPackage, output: Path) -> DevelopmentPackage:
    installed = metadata.distribution(package.name)
    if installed.version != package.version:
        msg = "development_package_version_does_not_match_lock"
        raise ValueError(msg)
    license_id, evidence = declared_license(installed)
    license_package = LicensePackage(
        ecosystem="python",
        name=package.name,
        version=package.version,
        license=license_id,
        evidence=evidence,
    )
    findings = license_findings(license_package)
    if findings:
        msg = "development_license_findings: " + str(findings)
        raise ValueError(msg)
    notices: list[RetainedFile] = []
    native: list[RetainedFile] = []
    verified = 0
    for file in installed.files or ():
        path = Path(str(installed.locate_file(file)))
        content = path.read_bytes()
        if file.hash is not None:
            if (
                file.hash.mode != "sha256"
                or base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
                != file.hash.value
            ):
                msg = "installed_RECORD_integrity_mismatch"
                raise ValueError(msg)
            verified += 1
        if ".dist-info/" in str(file) and any(
            v in file.name.upper() for v in ("LICENSE", "NOTICE")
        ):
            relative = Path(package.name) / str(file).split(".dist-info/", 1)[1]
            target = output / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            notices.append(_file_evidence(relative.as_posix(), content))
        if path.suffix in {".so", ".dylib", ".dll"}:
            native.append(_file_evidence(str(file), content))
    if not notices or not verified:
        msg = "missing_development_license_or_integrity_evidence"
        raise ValueError(msg)
    return DevelopmentPackage(
        package=license_package,
        requirements=tuple(installed.requires or ()),
        wheels=package.wheels,
        notices=tuple(notices),
        native_files=tuple(native),
        record_hashes_verified=verified,
    )


def inspect_wheel(wheel: Path) -> tuple[Message, int]:
    """Reject any FAISS package/member/metadata in the actual built product wheel."""
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if any("faiss" in name.lower() or name.startswith("scripts/") for name in names):
            msg = "development_code_in_product_wheel"
            raise ValueError(msg)
        name = next(n for n in names if n.endswith(".dist-info/METADATA"))
        message = BytesParser().parsebytes(archive.read(name))
        if "faiss" in str(message.get_all("Requires-Dist", ())).lower():
            msg = "faiss_in_wheel_runtime_dependencies"
            raise ValueError(msg)
    return message, len(names)


def audit(root: Path, wheel: Path, output: Path) -> DependencyReport:
    """Verify the precise approved three-package dev closure and disjoint product packaging."""
    lock = PythonLock.model_validate(tomllib.loads((root / "uv.lock").read_text()))
    project = ProjectManifest.model_validate(tomllib.loads((root / "pyproject.toml").read_text()))
    faiss = next(p for p in lock.packages if p.name == "faiss-cpu")
    selected = (faiss, *runtime_closure(lock, "faiss-cpu"))
    if {(p.name, p.version) for p in selected} != {
        ("faiss-cpu", "1.15.1"),
        ("numpy", "2.5.4"),
        ("packaging", "26.3"),
    }:
        msg = "development_closure_outside_approved_exact_versions"
        raise ValueError(msg)
    selection = tuple(SelectedPythonPackage(package=p) for p in selected)
    for item in selection:
        validate_requirements(item, tuple(metadata.requires(item.package.name) or ()), selection)
    runtime = runtime_closure(lock, project.project.name)
    if any(p.name == "faiss-cpu" for p in runtime):
        msg = "faiss_in_product_runtime_closure"
        raise ValueError(msg)
    if any("faiss" in p.read_text().lower() for p in (root / "datakeel").rglob("*.py")):
        msg = "faiss_in_product_python_source"
        raise ValueError(msg)
    message, count = inspect_wheel(wheel)
    return DependencyReport(
        development=tuple(_installed(p, output / "notices") for p in selected),
        runtime_names=tuple(sorted(p.name for p in runtime)),
        wheel_filename=wheel.name,
        wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
        wheel_requires_dist=tuple(message.get_all("Requires-Dist", ())),
        wheel_members=count,
    )


def main() -> None:
    """Write a bounded offline audit without fetching archives or replacing runtime notices."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/we/dependencies"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = audit(Path.cwd(), args.wheel, args.output)
    (args.output / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    Console().print(f"Development packages: {len(report.development)}; product FAISS: absent")


if __name__ == "__main__":
    main()
