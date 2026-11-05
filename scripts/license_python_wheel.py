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
from importlib.metadata import PathDistribution
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
# uv's venv bootstrap is not a distribution. Only this exact source/.pth pair is allowed;
# an installer-looking filename or a pyvenv.cfg marker alone cannot authorize source.
_VENV_BOOTSTRAP = {
    "_virtualenv.py": "cfb3db86aaa53bb62b5ff764970bec2d71c9228590a0ebec57f6ec926cc0bf1a",
    "_virtualenv.pth": "69ac3d8f27e679c81b94ab30b3b56e9cd138219b1ba94a1fa3606d5a76a1433d",
}


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
    except (OSError, ValueError, EOFError, TypeError, SyntaxError):
        return False


def _generated_file(relative: str, root: Path, expected: dict[str, bytes], info: str) -> bool:
    if relative in {f"{info}/{name}" for name in _INSTALLER_FILES}:
        return True
    return _bytecode(root / relative, root, expected)


def _other_record_files(root: Path, info: str) -> set[str]:
    owned: set[str] = set()
    for directory in root.glob("*.dist-info"):
        if directory.name == info or directory.is_symlink():
            continue
        distribution = PathDistribution(directory)
        if (
            distribution.read_text("RECORD") is None
            or not distribution.metadata.get("Name")
            or not distribution.metadata.get("Version")
        ):
            continue
        for file in distribution.files or ():
            # Wheel installers also record scripts outside site-packages. Those paths
            # cannot confer ownership inside this installation root.
            if (
                not file.is_absolute()
                and not {".", ".."}.intersection(file.parts)
                and (root / file).is_file()
                and not (root / file).is_symlink()
            ):
                owned.add(file.as_posix())
    return owned


def _venv_bootstrap(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for name, digest in _VENV_BOOTSTRAP.items():
        path = root / name
        if not path.is_file() or path.is_symlink():
            return {}
        contents = path.read_bytes()
        if hashlib.sha256(contents).hexdigest() != digest:
            return {}
        files[name] = contents
    return files


def _site_bytecode(path: Path, root: Path, sources: dict[str, bytes], owned: set[str]) -> bool:
    if path.suffix != ".pyc" or path.parent.name != "__pycache__":
        return False
    try:
        source = Path(importlib.util.source_from_cache(str(path)))
        name = source.relative_to(root).as_posix()
        if name not in sources and name in owned and source.is_file():
            sources[name] = source.read_bytes()
        return _bytecode(path, root, sources)
    except (OSError, ValueError):
        return False


def _site_entries(root: Path, owned: set[str], sources: dict[str, bytes]) -> None:
    # Check every top-level entry, independently of the MPL RECORD/wheel root set.
    # Other distributions own their roots through concrete RECORD descendants;
    # this is an ownership check, not a wheel integrity audit of every non-MPL package.
    directories = {name.split("/")[0] for name in owned if "/" in name}
    for path in root.iterdir():
        if path.is_symlink():
            _fail("installation contains an escaping path or symbolic link")
        if path.name == "__pycache__" and path.is_dir():
            _site_cache(path, root, sources, owned)
        elif path.is_dir() and path.name in directories:
            continue
        elif not path.is_file() or path.name not in owned:
            _fail("installation contains a top-level entry without a verified owner")


def _site_cache(cache: Path, root: Path, sources: dict[str, bytes], owned: set[str]) -> None:
    entries = tuple(cache.iterdir())
    if not entries:
        _fail("installation contains an unowned bytecode directory")
    for path in entries:
        if (
            path.is_symlink()
            or not path.is_file()
            or not _site_bytecode(path, root, sources, owned)
        ):
            _fail("installation contains bytecode without verifiable owned source")


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
    others = _other_record_files(root, info)
    bootstrap = _venv_bootstrap(root)
    sources = expected | bootstrap
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
            and name not in others
            and not _generated_file(name, root, expected, info)
            and not _site_bytecode(path, root, sources, others)
        ):
            _fail("installed wheel contains a file absent from the upstream archive")
    installers = {f"{info}/{name}" for name in _INSTALLER_FILES}
    _site_entries(root, set(expected) | others | installers | set(bootstrap), sources)


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
