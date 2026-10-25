# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve optional-package metadata against exact reviewed source and license bytes."""

from __future__ import annotations

import hashlib
from importlib import metadata
from typing import TYPE_CHECKING

from datakeel.core.models import BoundaryModel

if TYPE_CHECKING:
    from scripts.license_models import LicensePackage


class _ReviewedLicense(BoundaryModel):
    name: str
    version: str
    declared: str
    license: str
    files: dict[str, str]


_REVIEWED = (
    _ReviewedLicense(
        name="colorlog",
        version="6.12.0",
        declared="MIT License",
        license="MIT",
        files={"LICENSE": "b1d9082bc483623fd59fc7279b457f0e40d942a76426cde257239e04dfe4125a"},
    ),
    _ReviewedLicense(
        name="flatbuffers",
        version="25.12.19",
        declared="Apache 2.0",
        license="Apache-2.0",
        files={
            "flatbuffers/__init__.py": (
                "bc966ba9938e4ca74134c6bf89329403a5891bf73f373286a455ce7b5220b62c"
            )
        },
    ),
    _ReviewedLicense(
        name="omegaconf",
        version="2.4.0",
        declared="UNKNOWN",
        license="BSD-3-Clause",
        files={
            "LICENSE": "b31375ed5d5cbe7ec2d0c4c14df8afa7a8e5501bbe25f70b6cbc461685f4b91a",
            "LICENSE-antlr4": "3db1fb3ee79a4b4f9918fc4d0f6133bf18a3cf787f126cd22f8aa9b862281c0c",
        },
    ),
    _ReviewedLicense(
        name="onnxruntime",
        version="1.31.0",
        declared="MIT License",
        license="MIT",
        files={
            "onnxruntime/LICENSE": (
                "2f07c72751aed99790b8a4869cf2311df85a860b22ded05fa22803587a48922c"
            )
        },
    ),
    _ReviewedLicense(
        name="opencv-python-headless",
        version="5.0.0.93",
        declared="Apache 2.0",
        license="Apache-2.0 AND MIT",
        files={
            "LICENSE.txt": "09d719058e782ac7bc71ba21c944e1136cde2bb957c0e888121f0218d6b5f02c",
            "LICENSE-3RD-PARTY.txt": (
                "2537f5653345db7231ff12f307bcfa4c89807d45ed1c4bb8ebfb6f26f61b160a"
            ),
        },
    ),
    _ReviewedLicense(
        name="protobuf",
        version="7.36.2",
        declared="3-Clause BSD License",
        license="BSD-3-Clause",
        files={"LICENSE": "6e5e117324afd944dcf67f36cf329843bc1a92229a8cd9bb573d7a83130fea7d"},
    ),
)


def reviewed_ocr_license(package: LicensePackage) -> LicensePackage:
    """Accept a normalized identifier only if name, version, declaration and every hash match."""
    for reviewed in _REVIEWED:
        if (package.name, package.version, package.license) != (
            reviewed.name,
            reviewed.version,
            reviewed.declared,
        ):
            continue
        distribution = metadata.distribution(package.name)
        verified: list[str] = []
        for name, expected in reviewed.files.items():
            matches = [
                file for file in distribution.files or () if str(file) == name or file.name == name
            ]
            if not any(
                hashlib.sha256(file.read_binary()).hexdigest() == expected for file in matches
            ):
                return package
            verified.append(f"{name} SHA-256 {expected}")
        return package.model_copy(
            update={"license": reviewed.license, "evidence": "; ".join(verified)}
        )
    return package
