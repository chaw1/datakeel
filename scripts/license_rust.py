# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Audit all locked Rust dependency targets, including build and procedural macro crates."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import tomllib
from collections import deque
from pathlib import Path

from pydantic import Field
from rich.console import Console

from datakeel.core.errors import ValidationError
from scripts.license_models import LicensePackage, ManifestModel


class CargoPackage(ManifestModel):
    """Read a crate identity and its exact SPDX declaration from Cargo metadata."""

    id: str
    name: str
    version: str
    license: str | None = None
    manifest_path: Path


class CargoNode(ManifestModel):
    """Read resolved edges across every platform in the locked dependency graph."""

    id: str
    dependencies: tuple[str, ...]


class CargoResolve(ManifestModel):
    """Identify the selected root crate and resolved transitive dependency nodes."""

    root: str
    nodes: tuple[CargoNode, ...]


class CargoMetadata(ManifestModel):
    """Read Cargo's complete immutable dependency graph."""

    packages: tuple[CargoPackage, ...]
    resolve: CargoResolve


class CargoLockedPackage(ManifestModel):
    """Read the independently committed package identity before consulting its license."""

    name: str
    version: str


class CargoLock(ManifestModel):
    """Read package identities from Cargo's lockfile without resolving new versions."""

    packages: tuple[CargoLockedPackage, ...] = Field(alias="package")


def _metadata(root: Path) -> CargoMetadata:
    cargo = shutil.which("cargo")
    if not cargo:
        msg = "Rust toolchain is required; install Rust with rustup, then run make check"
        raise ValidationError(msg)
    try:
        result = subprocess.run(  # noqa: S603  # Fixed Cargo subcommand and local manifest.
            [
                cargo,
                "metadata",
                "--locked",
                "--format-version=1",
                "--manifest-path",
                str(root / "accel" / "Cargo.toml"),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as error:
        msg = "Locked Rust metadata is unavailable; run cargo fetch --locked in accel"
        raise ValidationError(msg) from error
    return CargoMetadata.model_validate_json(result.stdout)


def _selected_packages(metadata: CargoMetadata) -> tuple[CargoPackage, ...]:
    packages = {package.id: package for package in metadata.packages}
    nodes = {node.id: node for node in metadata.resolve.nodes}
    pending = deque([metadata.resolve.root])
    selected: set[str] = set()
    while pending:
        identity = pending.popleft()
        if identity in selected:
            continue
        if identity not in packages or identity not in nodes:
            msg = "Cargo metadata contains an unresolved dependency identity"
            raise ValidationError(msg)
        selected.add(identity)
        pending.extend(nodes[identity].dependencies)
    selected.remove(metadata.resolve.root)
    return tuple(
        sorted(
            (packages[identity] for identity in selected),
            key=lambda package: (package.name, package.version),
        )
    )


def metadata_packages(metadata: CargoMetadata) -> tuple[LicensePackage, ...]:
    """Follow the selected root's complete closure and retain unknown license declarations."""
    return tuple(
        LicensePackage(
            ecosystem="rust",
            name=package.name,
            version=package.version,
            license=package.license or "UNKNOWN",
            evidence="Cargo.lock identity / cargo metadata --locked SPDX declaration (all targets)",
        )
        for package in _selected_packages(metadata)
    )


def rust_packages(root: Path) -> tuple[LicensePackage, ...]:
    """Require the lockfile and resolve every selected Rust crate before license checks."""
    lock_path = root / "accel" / "Cargo.lock"
    if not lock_path.is_file():
        msg = "accel/Cargo.lock is required for the Rust license audit"
        raise ValidationError(msg)
    lock = CargoLock.model_validate(tomllib.loads(lock_path.read_text()))
    locked = {(package.name, package.version) for package in lock.packages}
    packages = metadata_packages(_metadata(root))
    if any((package.name, package.version) not in locked for package in packages):
        msg = "Cargo metadata identity differs from accel/Cargo.lock"
        raise ValidationError(msg)
    return packages


def render_rust_notices(metadata: CargoMetadata) -> str:
    """Preserve selected upstream license and notice texts without local registry paths."""
    sections = [
        "Third-party Rust dependency licenses",
        "Generated from accel/Cargo.lock using cargo metadata --locked (all targets).",
        "",
    ]
    for package in _selected_packages(metadata):
        source = package.manifest_path.parent
        files = sorted(
            {
                file
                for pattern in ("LICENSE*", "LICENCE*", "COPYING*", "NOTICE*")
                for file in source.glob(pattern)
                if file.is_file()
            }
        )
        if not files:
            msg = f"Rust crate {package.name} {package.version} has no upstream license text"
            raise ValidationError(msg)
        sections.extend(
            ["=" * 72, f"{package.name} {package.version}", package.license or "UNKNOWN"]
        )
        for file in files:
            sections.extend(["", file.name, "-" * 72, file.read_text().rstrip(), ""])
    return "\n".join(sections) + "\n"


def main() -> None:
    """Print the Rust inventory and fail on any non-permitted SPDX term."""
    from scripts.license_audit import license_findings  # noqa: PLC0415  # Avoid audit cycle.

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--write-notices", action="store_true")
    args = parser.parse_args()
    console = Console()
    findings = []
    for package in rust_packages(args.root):
        console.print(f"rust: {package.name} {package.version}: {package.license}", markup=False)
        findings.extend(license_findings(package))
    for finding in findings:
        console.print(f"FAIL {finding.name}: {finding.reason}", markup=False)
    if args.write_notices and not findings:
        destination = args.root / "accel/python/datakeel_accel/licenses/THIRD_PARTY_LICENSES.txt"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render_rust_notices(_metadata(args.root)))
    raise SystemExit(bool(findings))


if __name__ == "__main__":
    main()
