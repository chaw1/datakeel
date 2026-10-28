# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed dependency manifests, license evidence, and audit results."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from datakeel.core.models import BoundaryModel


class ManifestModel(BaseModel):
    """Read immutable external manifests, ignoring fields unrelated to dependency auditing."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class LockedDependency(ManifestModel):
    """Resolve one locked dependency with its selected extras and environment condition."""

    name: str
    version: str | None = None
    extras: tuple[str, ...] = Field(default=(), alias="extra")
    marker: str | None = None


class LockedPackage(ManifestModel):
    """Retain runtime edges separately from unselected optional and development dependencies."""

    name: str
    version: str
    dependencies: tuple[LockedDependency, ...] = ()
    optional_dependencies: dict[str, tuple[LockedDependency, ...]] = Field(
        default_factory=dict, alias="optional-dependencies"
    )
    resolution_markers: tuple[str, ...] = Field(default=(), alias="resolution-markers")


class PythonLock(ManifestModel):
    """Read the complete universal Python lock graph."""

    packages: tuple[LockedPackage, ...] = Field(alias="package")


class PythonProject(ManifestModel):
    """Identify the project's runtime dependency root."""

    name: str
    dependencies: tuple[str, ...] = ()


class SelectedPythonPackage(BoundaryModel):
    """Pair a resolved package with every extra selected by the runtime dependency graph."""

    package: LockedPackage
    extras: tuple[str, ...] = ()


class ProjectManifest(ManifestModel):
    """Read project identity without mixing in development dependency groups."""

    project: PythonProject


class PeerMetadata(ManifestModel):
    """Identify optional peers that need not be installed or bundled."""

    optional: bool = False


class FrontendPackage(ManifestModel):
    """Read npm runtime, optional, and peer edges without relying on a direct-package list."""

    name: str = ""
    version: str = ""
    license: str | None = None
    dependencies: dict[str, str] = Field(default_factory=dict)
    optional_dependencies: dict[str, str] = Field(
        default_factory=dict, alias="optionalDependencies"
    )
    peer_dependencies: dict[str, str] = Field(default_factory=dict, alias="peerDependencies")
    peer_metadata: dict[str, PeerMetadata] = Field(
        default_factory=dict, alias="peerDependenciesMeta"
    )


class FrontendLock(ManifestModel):
    """Bind npm package locations to exact versions and production dependency edges."""

    lockfile_version: int = Field(alias="lockfileVersion", ge=2)
    packages: dict[str, FrontendPackage]


class LicensePackage(BoundaryModel):
    """Describe one shipped dependency and the metadata supporting its SPDX identity."""

    ecosystem: Literal["python", "frontend", "rust", "sandbox-python"]
    name: str
    version: str
    license: str
    evidence: str


class LicenseFinding(BoundaryModel):
    """Explain one dependency that fails the declared license policy."""

    ecosystem: Literal["python", "frontend", "rust", "sandbox-python"]
    name: str
    version: str
    license: str
    reason: str


class LicenseReport(BoundaryModel):
    """Publish the measured runtime inventory and every non-compliant license."""

    python_target: str
    packages: tuple[LicensePackage, ...]
    findings: tuple[LicenseFinding, ...]


class LicenseFileEvidence(BoundaryModel):
    """Resolve ambiguous legacy metadata only against a reviewed, unchanged license file."""

    name: str
    version: str
    declared: str = ""
    declared_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    filename: str
    sha256: str
    license: str


class BundleInventory(BoundaryModel):
    """Bind measured Vite dependency locations to the exact frontend source and lock bytes."""

    schema_version: Literal[1]
    source_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    packages: tuple[str, ...]
