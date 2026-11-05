# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated offline distributions exercise the conditional MPL provenance boundary."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import tarfile
import zipfile
from importlib.metadata import PathDistribution
from typing import TYPE_CHECKING

import pytest

from datakeel.core.errors import ValidationError
from scripts import license_python
from scripts.license_audit import license_findings, render_notices
from scripts.license_frontend import frontend_packages
from scripts.license_models import LicenseReport
from scripts.license_mpl import https_source
from scripts.license_sandbox import sandbox_packages
from tests.test_license_frontend import write_frontend, write_inventory

if TYPE_CHECKING:
    from pathlib import Path


def write_python(root: Path, monkeypatch: pytest.MonkeyPatch) -> PathDistribution:
    """Generate a registry lock and installed wheel RECORD with no downloaded source."""
    (root / "pyproject.toml").write_text(
        '[project]\nname="application"\ndependencies=["generated==1.0"]\n'
    )
    site = root / "site"
    directory = site / "generated-1.0.dist-info"
    directory.mkdir(parents=True)
    (directory / "METADATA").write_text(
        "Metadata-Version: 2.4\nName: generated\nVersion: 1.0\nLicense-Expression: MPL-2.0\n"
        "Project-URL: Source, https://example.org/generated/source\n"
    )
    (directory / "LICENSE").write_text("Generated MPL license fixture\n")
    (site / "generated.py").write_text('"""Generated upstream module."""\n')
    (directory / "WHEEL").write_text(
        "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    )
    write_record(site)
    store = root / "wheels"
    store.mkdir()
    monkeypatch.setenv("DATAKEEL_LICENSE_WHEEL_DIR", str(store))
    archive = store / "generated-1.0-py3-none-any.whl"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for path in sorted(site.rglob("*")):
            if path.is_file():
                wheel.write(path, path.relative_to(site).as_posix())
    pin = hashlib.sha256(archive.read_bytes()).hexdigest()
    (root / "uv.lock").write_text(
        '[[package]]\nname="application"\nversion="1"\n'
        'dependencies=[{name="generated"}]\n'
        '[[package]]\nname="generated"\nversion="1.0"\n'
        'source={registry="https://example.org/simple"}\n'
        'wheels=[{url="https://example.org/' + archive.name + '",hash="sha256:' + pin + '"}]\n'
    )
    return PathDistribution(directory)


def write_record(site: Path) -> None:
    """Record SHA-256 hashes exactly as a wheel installer would."""
    directory = site / "generated-1.0.dist-info"
    rows: list[str] = []
    for path in sorted(site.rglob("*")):
        if path.is_file() and path.name != "RECORD":
            content = path.read_bytes()
            digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=")
            rows.append(
                f"{path.relative_to(site).as_posix()},sha256={digest.decode()},{len(content)}"
            )
    (directory / "RECORD").write_text("\n".join([*rows, "generated-1.0.dist-info/RECORD,,"]) + "\n")


def python_inventory(root: Path, monkeypatch: pytest.MonkeyPatch) -> LicenseReport:
    """Audit generated installed metadata through the real Python closure collector."""
    distribution = PathDistribution(root / "site/generated-1.0.dist-info")

    def installed_distribution(_name: str) -> PathDistribution:
        return distribution

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    packages = license_python.python_packages(root)
    return LicenseReport(
        python_target="generated",
        packages=packages,
        findings=tuple(finding for package in packages for finding in license_findings(package)),
    )


def test_python_mpl_notices_include_locked_identity_source_and_retained_licenses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real collector publishes required provenance fields for an unchanged generated wheel."""
    write_python(tmp_path, monkeypatch)
    report = python_inventory(tmp_path, monkeypatch)
    assert not report.findings
    notices = render_notices(report)
    assert "| python | generated | 1.0 | MPL-2.0 |" in notices
    assert "https://example.org/generated/source" in notices
    assert "LICENSE SHA-256" in notices
    assert "RECORD SHA-256 verified" in notices


@pytest.mark.parametrize(
    "mutation", ["source", "http", "local", "hash", "notice", "changed", "record", "extra"]
)
def test_python_mpl_rejects_missing_provenance_or_modified_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """Version and license metadata alone cannot authorize modified or unpinned MPL code."""
    distribution = write_python(tmp_path, monkeypatch)
    site = tmp_path / "site"
    metadata = site / "generated-1.0.dist-info/METADATA"
    lock = tmp_path / "uv.lock"
    if mutation == "source":
        metadata.write_text(metadata.read_text().split("Project-URL:")[0])
        write_record(site)
        assert python_inventory(tmp_path, monkeypatch).findings
        return
    if mutation == "http":
        metadata.write_text(metadata.read_text().replace("https://", "http://"))
        write_record(site)
        assert python_inventory(tmp_path, monkeypatch).findings
        return
    if mutation == "local":
        (site / "generated-1.0.dist-info/direct_url.json").write_text(
            '{"dir_info":{"editable":true}}'
        )
    elif mutation == "hash":
        lock.write_text(lock.read_text().replace("sha256:", "invalid:"))
    elif mutation == "notice":
        (site / "generated-1.0.dist-info/LICENSE").unlink()
        write_record(site)
    elif mutation == "changed":
        (site / "generated.py").write_text("modified = True\n")
    elif mutation == "record":
        (site / "generated-1.0.dist-info/RECORD").unlink()
    else:
        # A package directory also checks for source files absent from RECORD.
        module = site / "generated"
        module.mkdir()
        (module / "__init__.py").write_text("original = True\n")
        write_record(site)
        (module / "injected.py").write_text("modified = True\n")

    def installed_distribution(_name: str) -> PathDistribution:
        return distribution

    monkeypatch.setattr(license_python.metadata, "distribution", installed_distribution)
    assert python_inventory(tmp_path, monkeypatch).findings


def test_python_mpl_rejects_modified_source_with_rewritten_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rewriting installed RECORD cannot authorize source that differs from the locked wheel."""
    write_python(tmp_path, monkeypatch)
    assert not python_inventory(tmp_path, monkeypatch).findings
    (tmp_path / "site/generated.py").write_text("modified = True\n")
    write_record(tmp_path / "site")
    assert python_inventory(tmp_path, monkeypatch).findings


def write_npm(root: Path, monkeypatch: pytest.MonkeyPatch, *, source: bool = True) -> Path:
    """Create an MPL npm fixture and an integrity-locked tarball in an isolated offline cache."""
    web = write_frontend(root)
    directory = web / "node_modules/leaf"
    package = {
        "name": "leaf",
        "version": "1",
        "license": "MPL-2.0",
        "repository": {"type": "git", "url": "git+https://example.org/leaf/source.git"},
    }
    if not source:
        package.pop("repository")
    (directory / "package.json").write_text(json.dumps(package))
    (directory / "LICENSE").write_text("Generated MPL license\n")
    (directory / "index.js").write_text("export const generated = true;\n")
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        for path in sorted(directory.iterdir()):
            archive.add(path, arcname="package/" + path.name)
    content = stream.getvalue()
    digest = hashlib.sha512(content).digest()
    cache = root / "npm-cache"
    monkeypatch.setenv("NPM_CONFIG_CACHE", str(cache))
    hex_digest = digest.hex()
    cached = (
        cache / "_cacache/content-v2/sha512" / hex_digest[:2] / hex_digest[2:4] / hex_digest[4:]
    )
    cached.parent.mkdir(parents=True)
    cached.write_bytes(content)
    lock_path = web / "package-lock.json"
    lock = json.loads(lock_path.read_text())
    lock["packages"]["node_modules/leaf"] = {
        **package,
        "resolved": "https://example.org/leaf-1.tgz",
        "integrity": "sha512-" + base64.b64encode(digest).decode(),
    }
    lock_path.write_text(json.dumps(lock))
    write_inventory(root)
    return directory


def test_frontend_mpl_requires_unchanged_locked_archive_and_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Frontend MPL metadata is accepted with actual cached-archive and notice evidence."""
    write_npm(tmp_path, monkeypatch)
    package = frontend_packages(tmp_path)[0]
    assert not license_findings(package)
    assert package.mpl is not None
    assert package.mpl.source_url == "https://example.org/leaf/source"
    report = LicenseReport(python_target="generated", packages=(package,), findings=())
    notices = render_notices(report)
    assert "| frontend | leaf | 1 | MPL-2.0 |" in notices
    assert "https://example.org/leaf/source" in notices


def test_frontend_mpl_missing_source_is_a_policy_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An intact upstream archive without a source URL cannot silently pass the audit."""
    write_npm(tmp_path, monkeypatch, source=False)
    package = frontend_packages(tmp_path)[0]
    assert license_findings(package)


@pytest.mark.parametrize(
    "mutation", ["source", "changed", "extra", "notice", "pin", "local", "cache"]
)
def test_frontend_mpl_rejects_unproven_or_changed_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    """An unchanged version and license do not hide source drift or lost integrity evidence."""
    directory = write_npm(tmp_path, monkeypatch)
    path = tmp_path / "web/package-lock.json"
    lock = json.loads(path.read_text())
    if mutation == "source":
        installed = json.loads((directory / "package.json").read_text())
        installed.pop("repository")
        (directory / "package.json").write_text(json.dumps(installed))
    elif mutation == "changed":
        (directory / "index.js").write_text("modified = true;\n")
    elif mutation == "extra":
        (directory / "injected.js").write_text("modified = true;\n")
    elif mutation == "notice":
        (directory / "LICENSE").unlink()
    elif mutation == "pin":
        lock["packages"]["node_modules/leaf"]["integrity"] = ""
    elif mutation == "local":
        lock["packages"]["node_modules/leaf"]["resolved"] = "file:local-copy.tgz"
    else:
        for cached in (tmp_path / "npm-cache").rglob("*"):
            if cached.is_file():
                cached.write_bytes(b"changed")
    path.write_text(json.dumps(lock))
    write_inventory(tmp_path)
    with pytest.raises(ValidationError, match="MPL provenance"):
        frontend_packages(tmp_path)


@pytest.mark.parametrize(
    "url",
    [
        "",
        "http://example.org/source",
        "https://[",
        "https://example.org",
        "https://user:secret@example.org/source",
    ],
)
def test_mpl_source_address_must_be_concrete_https_without_credentials(url: str) -> None:
    """Source evidence must be usable as a public HTTPS link without a network request."""
    assert not https_source(url)


def test_sandbox_projection_preserves_mpl_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sandbox collector carries the same checked provenance instead of waiving it."""
    write_python(tmp_path, monkeypatch)
    package = python_inventory(tmp_path, monkeypatch).packages[0]
    directory = tmp_path / "sandbox"
    directory.mkdir()
    (directory / "Dockerfile").write_text(
        "FROM python:3.12@sha256:" + "0" * 64 + "\n"
        "RUN pip install --no-cache-dir --no-deps numpy==1.0.0 Pillow==1.0.0\n"
    )
    packages = tuple(
        package.model_copy(update={"name": name, "version": "1.0.0"})
        for name in ("numpy", "pillow")
    )
    selected = sandbox_packages(tmp_path, packages)
    assert all(item.mpl == package.mpl and not license_findings(item) for item in selected)
    assert all(item.ecosystem == "sandbox-python" for item in selected)
