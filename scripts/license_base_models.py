# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen evidence inventory for the separately distributed official base image."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from datakeel.core.models import BoundaryModel


class ImageLicenseFile(BoundaryModel):
    """Identify an upstream copyright file retained inside the image."""

    path: str = Field(pattern=r"^/usr/(?:share/doc/|local/)[^\n]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def safe_path(self) -> "ImageLicenseFile":
        """Keep evidence paths inside the public image rather than a host filesystem."""
        if ".." in self.path.split("/") or "\\" in self.path:
            msg = "Invalid image license evidence path"
            raise ValueError(msg)
        return self


class BasePythonRuntime(BoundaryModel):
    """Record the interpreter and its unchanged upstream license notice."""

    version: str = Field(pattern=r"^3\.12\.[0-9]+$")
    license: Literal["PSF-2.0"]
    evidence: ImageLicenseFile


class BasePythonPackage(BoundaryModel):
    """Retain complete installed wheel license files, including vendored notices."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    license: str = Field(min_length=1)
    evidence: tuple[ImageLicenseFile, ...] = Field(min_length=1)


class BaseOSPackage(BoundaryModel):
    """Preserve Debian license declarations without applying the Python allowlist."""

    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    architecture: str = Field(min_length=1)
    copyright: ImageLicenseFile
    licenses: tuple[Annotated[str, Field(min_length=1)], ...] = Field(min_length=1)

    @model_validator(mode="after")
    def package_notice(self) -> "BaseOSPackage":
        """Bind each package's evidence to its retained upstream copyright notice."""
        if self.copyright.path != f"/usr/share/doc/{self.name}/copyright":
            msg = "OS package evidence must identify that package's copyright notice"
            raise ValueError(msg)
        return self


class CollectedBaseInventory(BoundaryModel):
    """Require copyright evidence for every package reported by dpkg and Python metadata."""

    python: BasePythonRuntime
    python_packages: tuple[BasePythonPackage, ...] = Field(min_length=1)
    os_packages: tuple[BaseOSPackage, ...] = Field(min_length=1)


class BaseImageInventory(CollectedBaseInventory):
    """Bind collected evidence to its pinned image reference and measured platform."""

    schema_version: Literal[1] = 1
    base_reference: str = Field(pattern=r"^python:[^ @]+@sha256:[0-9a-f]{64}$")
    image_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    platform: str = Field(pattern=r"^linux/(?:arm64|amd64)$")
    os_package_count: int = Field(ge=1)

    @model_validator(mode="after")
    def complete_packages(self) -> "BaseImageInventory":
        """Reject partial or duplicate package inventories."""
        names = [package.name for package in self.os_packages]
        python_names = [package.name.lower() for package in self.python_packages]
        if (
            len(names) != self.os_package_count
            or len(names) != len(set(names))
            or len(python_names) != len(set(python_names))
        ):
            msg = "Base image package inventory is incomplete or contains duplicates"
            raise ValueError(msg)
        return self
