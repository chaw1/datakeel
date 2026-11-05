# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind installed MPL files to an actual offline wheel whose bytes match uv.lock."""

from __future__ import annotations

import hashlib
import importlib.util
import io
import marshal
import os
import re
import stat
import zipfile
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, NoReturn
from urllib.parse import unquote, urlsplit

from packaging.tags import sys_tags
from packaging.utils import InvalidWheelFilename, canonicalize_name, parse_wheel_filename

from datakeel.core.errors import ValidationError

if TYPE_CHECKING:
    from importlib.metadata import Distribution

    from scripts.license_models import LockedArtifact, LockedPackage

_WHEEL_DATA_PARTS = 3
_INSTALLER_FILES = frozenset({"INSTALLER", "REQUESTED", "RECORD", "uv_cache.json", "uv_build.json"})


def _fail(message: str) -> NoReturn:
    raise ValidationError("MPL provenance: " + message)


def _wheel_name(artifact: LockedArtifact, package: LockedPackage) -> str:
    name = unquote(urlsplit(artifact.url).path.rsplit("/", 1)[-1])
    try:
        project, version, _, tags = parse_wheel_filename(name)
    except InvalidWheelFilename:
        return ""
    if (
        canonicalize_name(package.name) != project
        or str(version) != package.version
        or not tags.intersection(sys_tags())
    ):
        return ""
    return name


def _safe_member(member: zipfile.ZipInfo) -> str:
    name = member.filename
    if (
        not name
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or PurePosixPath(name).is_absolute()
        or "\\" in name
        or stat.S_ISLNK(member.external_attr >> 16)
    ):
        _fail("wheel contains an unsafe path or symbolic link")
    return name


def _wheel_files(payload: bytes, package: LockedPackage) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as wheel:
            for member in wheel.infolist():
                if member.is_dir():
                    continue
                name = _safe_member(member)
                if name in files:
                    _fail("wheel contains duplicate paths")
                files[name] = wheel.read(member)
    except (OSError, zipfile.BadZipFile, RuntimeError) as error:
        _fail(f"cannot read locked wheel: {type(error).__name__}")
    metadata = [name for name in files if name.endswith(".dist-info/METADATA")]
    if len(metadata) != 1:
        _fail("wheel must have exactly one distribution METADATA")
    identity = BytesParser().parsebytes(files[metadata[0]])
    if (
        canonicalize_name(identity.get("Name", "")) != canonicalize_name(package.name)
        or identity.get("Version") != package.version
    ):
        _fail("wheel identity differs from uv.lock")
    return files


def _installed_layout(files: dict[str, bytes]) -> tuple[dict[str, bytes], str]:
    info = next(name.split("/")[0] for name in files if name.endswith(".dist-info/METADATA"))
    expected: dict[str, bytes] = {}
    data = info.removesuffix(".dist-info") + ".data"
    for archive_name, contents in files.items():
        name = archive_name
        parts = archive_name.split("/")
        if parts[0].endswith(".dist-info") and parts[0] != info:
            _fail("wheel contains a second distribution directory")
        if parts[0].endswith(".data"):
            if (
                len(parts) < _WHEEL_DATA_PARTS
                or parts[0] != data
                or parts[1] not in {"purelib", "platlib"}
            ):
                _fail("wheel installation scheme cannot be mapped reliably")
            name = "/".join(parts[2:])
        if name in expected:
            _fail("wheel paths collide after installation mapping")
        expected[name] = contents
    if f"{info}/WHEEL" not in expected or f"{info}/RECORD" not in expected:
        _fail("wheel is missing WHEEL or RECORD metadata")
    return expected, info


def _bytecode(path: Path, root: Path, expected: dict[str, bytes]) -> bool:
    if path.suffix != ".pyc" or path.parent.name != "__pycache__":
        return False
    try:
        source = Path(importlib.util.source_from_cache(str(path)))
        contents = expected.get(source.relative_to(root).as_posix())
        if contents is None:
            return False
        payload = path.read_bytes()
        if payload[:4] != importlib.util.MAGIC_NUMBER:
            return False
        optimization = re.search(r"\.opt-([12])\.pyc$", path.name)
        level = int(optimization[1]) if optimization else 0
        # Compare with compilation of locked source; never execute installed bytecode.
        code = compile(contents, str(source), "exec", optimize=level, dont_inherit=True)
        stream = io.BytesIO(payload[16:])
        cached: object = marshal.load(stream)  # noqa: S302  # Compared only; never executed.
        return cached == code and not stream.read()
    except (OSError, ValueError, EOFError, TypeError):
        return False


def _generated_file(relative: str, root: Path, expected: dict[str, bytes], info: str) -> bool:
    if relative in {f"{info}/{name}" for name in _INSTALLER_FILES}:
        return True
    return _bytecode(root / relative, root, expected)


def _compare_installation(distribution: Distribution, files: dict[str, bytes]) -> None:
    root = Path(str(distribution.locate_file(""))).absolute()
    expected, info = _installed_layout(files)
    for name, contents in expected.items():
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            _fail("installed wheel path escapes its installation root")
        if not path.is_file():
            _fail("installed wheel is missing an upstream file")
        if name != f"{info}/RECORD" and path.read_bytes() != contents:
            _fail("installed file differs from the hash-verified upstream wheel")
    _installed_extras(root, distribution, expected, info)


def _installed_extras(
    root: Path, distribution: Distribution, expected: dict[str, bytes], info: str
) -> None:
    actual = {str(file) for file in distribution.files or ()}
    for first in {name.split("/")[0] for name in expected}:
        top = root / first
        if top.is_dir():
            actual.update(path.relative_to(root).as_posix() for path in top.rglob("*"))
        elif top.suffix == ".py":
            if top.with_suffix("").exists():
                _fail("installed module is shadowed by an extra package directory")
            actual.update(
                path.relative_to(root).as_posix()
                for path in (root / "__pycache__").glob(top.stem + ".*.pyc")
            )
    for name in actual:
        path = root / name
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            _fail("installed wheel contains an escaping path or symbolic link")
        if (
            path.is_file()
            and name not in expected
            and not _generated_file(name, root, expected, info)
        ):
            _fail("installed wheel contains a file absent from the upstream archive")


def verify_installed_wheel(package: LockedPackage, distribution: Distribution) -> str:
    """Read actual locked wheel bytes and verify every upstream file and installed layout.

    DATAKEEL_LICENSE_WHEEL_DIR supplies retained original wheel files, named as in uv.lock.
    The fallback is UV_CACHE_DIR/license-wheels; unpacked uv caches are never trusted as wheels.
    Source builds fail closed because an sdist alone cannot prove installed build output.
    """
    cache = Path(os.environ.get("UV_CACHE_DIR", str(Path.home() / ".cache/uv")))
    store = Path(os.environ.get("DATAKEEL_LICENSE_WHEEL_DIR", str(cache / "license-wheels")))
    available = [
        (artifact, name)
        for artifact in package.wheels
        if (name := _wheel_name(artifact, package)) and (store / name).is_file()
    ]
    if not available:
        _fail(
            "no actual compatible locked wheel in DATAKEEL_LICENSE_WHEEL_DIR; "
            "sdist builds are unsupported"
        )
    failures: list[str] = []
    for artifact, name in available:
        path = store / name
        try:
            payload = path.read_bytes()
            if (
                path.is_symlink()
                or "sha256:" + hashlib.sha256(payload).hexdigest() != artifact.hash
            ):
                _fail("actual wheel SHA-256 differs from uv.lock")
            _compare_installation(distribution, _wheel_files(payload, package))
        except ValidationError as error:
            failures.append(str(error).removeprefix("MPL provenance: "))
        else:
            return f"{name} {artifact.hash}; upstream wheel bytes and installation layout verified"
    _fail("; ".join(failures))
