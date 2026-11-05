# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Supply only certifi/orjson wheel evidence for CI; license_audit stays offline."""

from __future__ import annotations

import argparse
import hashlib
import re
import tempfile
import tomllib
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

import httpx
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from pydantic import Field

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from scripts.license_models import LockedPackage, ManifestModel
from scripts.license_python_wheel import validate_wheel_archive

if TYPE_CHECKING:
    from packaging.tags import Tag

_TARGETS = frozenset({"certifi", "orjson"})


class CiArtifact(ManifestModel):
    """Read exact wheel pins; uv's unrelated upload-time field is intentionally ignored."""

    url: str
    hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size: int = Field(strict=True, gt=0)


class CiPackage(ManifestModel):
    """Read registry wheels without interpreting unrelated dependency graph fields."""

    name: str
    version: str
    source: dict[str, str]
    wheels: tuple[CiArtifact, ...] = ()


class CiLock(ManifestModel):
    """Parse uv.lock, ignoring its unrelated resolver and project configuration."""

    packages: tuple[CiPackage, ...] = Field(alias="package")


class WheelPin(BoundaryModel):
    """Carry one selected, validated package and its original wheel download identity."""

    package: LockedPackage
    artifact: CiArtifact
    filename: str


def _filename(artifact: CiArtifact, package: CiPackage) -> tuple[str, frozenset[Tag]]:
    url = urlsplit(artifact.url)
    filename = url.path.rsplit("/", 1)[-1]
    if (
        url.scheme != "https"
        or url.netloc != "files.pythonhosted.org"
        or url.query
        or url.fragment
        or re.search(r"[\s\\]", artifact.url)
        or not re.fullmatch(r"/packages/(?:[a-f0-9]+/){3}[A-Za-z0-9_.+-]+\.whl", url.path)
    ):
        msg = "Wheel URL must be an exact files.pythonhosted.org HTTPS archive URL"
        raise ValidationError(msg)
    name, version, _, tags = parse_wheel_filename(filename)
    if name != canonicalize_name(package.name) or str(version) != package.version:
        msg = "Wheel filename identity differs from uv.lock package"
        raise ValidationError(msg)
    return filename, tags


def locked_wheels(lock_path: Path) -> tuple[WheelPin, ...]:
    """Select one compatible wheel per target; validate all target pins before any network I/O."""
    lock = CiLock.model_validate(tomllib.loads(lock_path.read_text()))
    ranks = {tag: index for index, tag in enumerate(sys_tags())}
    selected: list[WheelPin] = []
    for target in sorted(_TARGETS):
        matches = [p for p in lock.packages if canonicalize_name(p.name) == target]
        if len(matches) != 1 or matches[0].source != {"registry": "https://pypi.org/simple"}:
            msg = "CI evidence requires one locked PyPI registry package per target"
            raise ValidationError(msg)
        package = matches[0]
        candidates: list[tuple[int, WheelPin]] = []
        for artifact in package.wheels:
            filename, tags = _filename(artifact, package)
            compatible = tags.intersection(ranks)
            if compatible:
                pin = WheelPin(
                    package=LockedPackage(name=package.name, version=package.version),
                    artifact=artifact,
                    filename=filename,
                )
                candidates.append((min(ranks[tag] for tag in compatible), pin))
        if not candidates:
            msg = "No compatible locked wheel for CI evidence; source builds are unsupported"
            raise ValidationError(msg)
        selected.append(min(candidates, key=lambda item: (item[0], item[1].filename))[1])
    return tuple(selected)


def _validate(payload: bytes, pin: WheelPin) -> None:
    if (
        len(payload) != pin.artifact.size
        or "sha256:" + hashlib.sha256(payload).hexdigest() != pin.artifact.hash
    ):
        msg = "Wheel length or SHA-256 differs from uv.lock"
        raise ValidationError(msg)
    validate_wheel_archive(payload, pin.package)


def _download(client: httpx.Client, pin: WheelPin) -> bytes:
    with client.stream(
        "GET", pin.artifact.url, follow_redirects=False, headers={"Accept-Encoding": "identity"}
    ) as response:
        response.raise_for_status()
        if (
            response.status_code != HTTPStatus.OK
            or str(response.url) != pin.artifact.url
            or response.headers.get("content-encoding", "identity") != "identity"
            or (
                "content-length" in response.headers
                and response.headers["content-length"] != str(pin.artifact.size)
            )
        ):
            msg = "Wheel response differs from the exact locked request"
            raise ValidationError(msg)
        payload = bytearray()
        for chunk in response.iter_bytes():
            payload.extend(chunk)
            if len(payload) > pin.artifact.size:
                msg = "Wheel response exceeds the locked length"
                raise ValidationError(msg)
    return bytes(payload)


def supply_wheels(lock_path: Path, store: Path, client: httpx.Client) -> tuple[Path, ...]:
    """Reuse verified files or stage downloads; publish only after every target validates."""
    pins = locked_wheels(lock_path)
    store.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=store) as temporary:
        pending: list[tuple[Path, Path]] = []
        for pin in pins:
            path = store / pin.filename
            if path.is_symlink():
                msg = "Wheel evidence must be a regular file, not a symbolic link"
                raise ValidationError(msg)
            payload = path.read_bytes() if path.exists() else _download(client, pin)
            _validate(payload, pin)
            if not path.exists():
                staged = Path(temporary) / pin.filename
                staged.write_bytes(payload)
                pending.append((staged, path))
            paths.append(path)
        for staged, path in pending:
            staged.replace(path)
    return tuple(paths)


def main() -> None:
    """Export the evidence directory to subsequent CI steps only after complete validation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, default=Path("uv.lock"))
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--github-env", type=Path, required=True)
    args = parser.parse_args()
    store = args.wheel_dir.resolve()
    if "\n" in str(store) or "\r" in str(store):
        parser.error("Wheel directory cannot contain a newline")
    with httpx.Client(trust_env=False, follow_redirects=False, timeout=30) as client:
        supply_wheels(args.lock, store, client)
    with args.github_env.open("a") as environment:
        environment.write(f"DATAKEEL_LICENSE_WHEEL_DIR={store}\n")


if __name__ == "__main__":
    main()
