# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require offline provenance and retained notices for unchanged MPL distributions."""

from __future__ import annotations

import base64
import hashlib
import io
import os
import re
import tarfile
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn
from urllib.parse import urlsplit

from datakeel.core.errors import ValidationError
from scripts.license_models import LicenseFinding, MplEvidence
from scripts.license_python_wheel import verify_installed_wheel

if TYPE_CHECKING:
    from importlib.metadata import Distribution, PackagePath

    from scripts.license_models import FrontendPackage, LicensePackage, LockedPackage


def https_source(value: str) -> bool:
    """Accept a concrete HTTPS source location without credentials or Markdown delimiters."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return bool(
        parsed.scheme == "https"
        and parsed.hostname
        and parsed.path.strip("/")
        and not parsed.username
        and not parsed.password
        and not re.search(r"[\s|<>\\]", value)
    )


def uses_mpl(expression: str) -> bool:
    """Recognize an exact MPL term without accepting a substring as a license identifier."""
    return "MPL-2.0" in re.findall(r"[A-Za-z0-9][A-Za-z0-9.+-]*", expression)


def mpl_findings(package: LicensePackage) -> tuple[LicenseFinding, ...]:
    """Fail closed when an MPL runtime row has no checked provenance and source evidence."""
    evidence = package.mpl
    if (
        evidence
        and not evidence.failure
        and https_source(evidence.source_url)
        and evidence.integrity
        and evidence.notices
    ):
        return ()
    return (
        LicenseFinding(
            ecosystem=package.ecosystem,
            name=package.name,
            version=package.version,
            license=package.license,
            reason=(
                evidence.failure
                if evidence and evidence.failure
                else "MPL requires locked upstream integrity, retained notices and HTTPS source URL"
            ),
        ),
    )


def _fail(message: str) -> NoReturn:
    raise ValidationError("MPL provenance: " + message)


def _notice(name: str) -> bool:
    return name.upper().startswith(("LICENSE", "LICENCE", "COPYING", "NOTICE"))


def _record_file(file: PackagePath, path: Path) -> str | None:
    if file.suffix == ".pyc" or file.name == "RECORD":
        return None
    if file.hash is None or file.hash.mode != "sha256" or not path.is_file():
        _fail("installed file lacks SHA-256 RECORD evidence")
    digest = hashlib.sha256(path.read_bytes()).digest()
    if base64.urlsafe_b64encode(digest).rstrip(b"=").decode() != file.hash.value:
        _fail("installed file differs from its upstream RECORD")
    return f"{file.name} SHA-256 {digest.hex()}" if _notice(file.name) else None


def _python_files(distribution: Distribution) -> tuple[str, ...]:
    if distribution.read_text("direct_url.json") is not None:
        _fail("local, editable or direct-URL installations are not registry distributions")
    files = distribution.files or ()
    if not files:
        _fail("installed distribution has no RECORD")
    notices: list[str] = []
    root = Path(str(distribution.locate_file(""))).resolve()
    for file in files:
        path = Path(str(distribution.locate_file(file)))
        if not path.resolve().is_relative_to(root) or path.is_symlink():
            _fail("installed file escapes the upstream distribution")
        if notice := _record_file(file, path):
            notices.append(notice)
    if not notices:
        _fail("upstream license notices are missing")
    return tuple(sorted(notices))


def python_mpl_evidence(package: LockedPackage, distribution: Distribution) -> MplEvidence:
    """Return checked evidence or a finding reason for unverified installation data."""
    try:
        return _verified_python_evidence(package, distribution)
    except ValidationError as error:
        return MplEvidence(source_url="", integrity="", notices=(), failure=str(error))


def _verified_python_evidence(package: LockedPackage, distribution: Distribution) -> MplEvidence:
    if set(package.source) != {"registry"} or not https_source(package.source["registry"]):
        _fail("uv.lock must select an HTTPS upstream registry")
    artifacts = (*package.wheels, *((package.sdist,) if package.sdist else ()))
    if not artifacts or any(
        not https_source(item.url) or not re.fullmatch(r"sha256:[0-9a-f]{64}", item.hash)
        for item in artifacts
    ):
        _fail("uv.lock must retain HTTPS distribution URLs and SHA-256 pins")
    integrity = verify_installed_wheel(package, distribution)
    sources = (
        value.split(",", 1)[1].strip()
        for value in distribution.metadata.get_all("Project-URL", ())
        if value.split(",", 1)[0].strip().lower() in {"source", "source code", "repository", "code"}
        and "," in value
    )
    source = next((value for value in sources if https_source(value)), "")
    return MplEvidence(
        source_url=source,
        integrity=integrity + "; auxiliary installed RECORD SHA-256 verified",
        notices=_python_files(distribution),
    )


def _npm_archive(package: FrontendPackage) -> bytes:
    if not https_source(package.resolved):
        _fail("npm lock must select an HTTPS upstream distribution")
    match = re.fullmatch(r"(sha512|sha256)-([A-Za-z0-9+/]+={0,2})", package.integrity)
    if match is None:
        _fail("npm lock must retain a SHA-512 or SHA-256 integrity pin")
    algorithm, encoded = match.groups()
    digest = base64.b64decode(encoded).hex()
    cache = Path(os.environ.get("NPM_CONFIG_CACHE", str(Path.home() / ".npm")))
    archive = cache / "_cacache/content-v2" / algorithm / digest[:2] / digest[2:4] / digest[4:]
    if not archive.is_file():
        _fail("locked npm archive is absent from the offline cache; retain it with npm ci")
    contents = archive.read_bytes()
    if hashlib.new(algorithm, contents).hexdigest() != digest:
        _fail("npm archive differs from the locked integrity pin")
    return contents


def frontend_mpl_evidence(
    package: FrontendPackage, installed: FrontendPackage, directory: Path
) -> MplEvidence:
    """Compare installed npm files with the integrity-locked cached upstream tarball."""
    repository = installed.repository
    source = repository.get("url", "") if isinstance(repository, dict) else repository or ""
    source = source.removeprefix("git+").removesuffix(".git")
    expected: set[str] = set()
    notices: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(_npm_archive(package)), mode="r:gz") as archive:
        for member in archive.getmembers():
            relative = member.name.removeprefix("package/")
            if member.isdir():
                continue
            if (
                not member.isfile()
                or not member.name.startswith("package/")
                or any(part in {"", ".", ".."} for part in relative.split("/"))
            ):
                _fail("npm upstream archive contains an unsafe entry")
            file = archive.extractfile(member)
            path = directory / relative
            if file is None or path.is_symlink() or not path.is_file():
                _fail("installed npm distribution is incomplete")
            contents = file.read()
            if path.read_bytes() != contents:
                _fail("installed npm file differs from locked upstream archive")
            expected.add(relative)
            if _notice(path.name):
                notices.append(f"{relative} SHA-256 {hashlib.sha256(contents).hexdigest()}")
    actual = {
        path.relative_to(directory).as_posix()
        for path in directory.rglob("*")
        if path.is_file() and "node_modules" not in path.relative_to(directory).parts
    }
    if expected != actual or not notices:
        _fail("npm distribution has extra files or missing license notices")
    return MplEvidence(
        source_url=source,
        integrity="package-lock.json " + package.integrity + "; upstream archive files verified",
        notices=tuple(sorted(notices)),
    )
