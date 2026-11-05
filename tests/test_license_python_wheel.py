# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Offline wheel bytes, installation mappings and rewritten RECORD attacks stay bound."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import py_compile
import stat
import zipfile
from pathlib import Path

import pytest

from tests.test_license_mpl import python_inventory, write_python, write_record


def wheel_path(root: Path) -> Path:
    """Locate the independently generated fixture archive, never an upstream source copy."""
    return root / "wheels/generated-1.0-py3-none-any.whl"


def wheel_contents(root: Path) -> dict[str, bytes]:
    """Read generated wheel members before deliberately mutating them in a test."""
    with zipfile.ZipFile(wheel_path(root)) as wheel:
        return {name: wheel.read(name) for name in wheel.namelist()}


def repack_wheel(root: Path, contents: dict[str, bytes]) -> None:
    """Pin a newly generated archive independently of the mutable installation RECORD."""
    path = wheel_path(root)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    record = "generated-1.0.dist-info/RECORD"
    rows: list[str] = []
    for name, data in sorted(contents.items()):
        if name != record:
            digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            rows.append(f"{name},sha256={digest},{len(data)}")
    contents[record] = ("\n".join([*rows, record + ",,"]) + "\n").encode()
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in contents.items():
            wheel.writestr(name, data)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    lock = root / "uv.lock"
    lock.write_text(lock.read_text().replace(before, after))


@pytest.mark.parametrize("attack", ["missing", "zero_pin", "replaced", "truncated", "sdist_only"])
def test_locked_wheel_requires_actual_archive_and_matching_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    """Placeholder pins, unpacked data and sdist metadata cannot stand in for wheel bytes."""
    write_python(tmp_path, monkeypatch)
    assert not python_inventory(tmp_path, monkeypatch).findings
    path = wheel_path(tmp_path)
    lock = tmp_path / "uv.lock"
    if attack == "missing":
        path.unlink()
    elif attack == "zero_pin":
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lock.write_text(lock.read_text().replace(digest, "0" * 64))
    elif attack == "replaced":
        path.write_bytes(path.read_bytes() + b"modified archive")
    elif attack == "truncated":
        path.write_bytes(b"PK")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        text = lock.read_text()
        start = text.index('hash="sha256:') + len('hash="sha256:')
        lock.write_text(text[:start] + digest + text[start + 64 :])
    else:
        lines = lock.read_text().splitlines()
        lines[-1] = lines[-1].replace("wheels=[{", "sdist={").removesuffix("]")
        lock.write_text("\n".join(lines) + "\n")
    assert python_inventory(tmp_path, monkeypatch).findings


def test_pinned_archive_with_different_contents_cannot_authorize_installed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even a real matching archive hash must also match installed source bytes."""
    write_python(tmp_path, monkeypatch)
    contents = wheel_contents(tmp_path)
    contents["generated.py"] = b"different_upstream = True\n"
    repack_wheel(tmp_path, contents)
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize(
    "area", ["source", "license", "metadata", "extra", "omitted_extra", "shadow"]
)
def test_rewritten_record_cannot_hide_changed_or_additional_installed_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, area: str
) -> None:
    """The archive is the truth source even when all mutable installed hashes agree."""
    write_python(tmp_path, monkeypatch)
    site = tmp_path / "site"
    if area == "source":
        path = site / "generated.py"
    elif area == "license":
        path = site / "generated-1.0.dist-info/LICENSE"
    elif area == "metadata":
        path = site / "generated-1.0.dist-info/METADATA"
    elif area == "shadow":
        path = site / "generated/__init__.py"
        path.parent.mkdir()
    else:
        path = site / "generated-1.0.dist-info/injected.py"
    path.write_text(
        path.read_text() + "Summary: modified\n" if area == "metadata" else "modified = True\n"
    )
    if area != "omitted_extra":
        write_record(site)
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize("scheme", ["purelib", "platlib"])
def test_wheel_data_site_layout_is_verified_after_relocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    """Supported wheel data schemes map to the actual site root before byte comparison."""
    write_python(tmp_path, monkeypatch)
    contents = wheel_contents(tmp_path)
    contents[f"generated-1.0.data/{scheme}/generated.py"] = contents.pop("generated.py")
    repack_wheel(tmp_path, contents)
    assert not python_inventory(tmp_path, monkeypatch).findings
    (tmp_path / "site/generated.py").write_text("modified = True\n")
    write_record(tmp_path / "site")
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize("scheme", ["scripts", "headers", "data", "unknown"])
def test_unverifiable_wheel_data_layout_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, scheme: str
) -> None:
    """Installer transformations with no reliable mapping cannot receive MPL evidence."""
    write_python(tmp_path, monkeypatch)
    contents = wheel_contents(tmp_path)
    contents[f"generated-1.0.data/{scheme}/generated.py"] = contents.pop("generated.py")
    repack_wheel(tmp_path, contents)
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize(
    "attack", ["traversal", "absolute", "collision", "second_metadata", "identity"]
)
def test_hash_verified_archive_still_requires_safe_unique_package_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    """A trusted archive pin alone cannot excuse invalid paths or a different package identity."""
    write_python(tmp_path, monkeypatch)
    contents = wheel_contents(tmp_path)
    if attack == "traversal":
        contents["../escape.py"] = b"bad"
    elif attack == "absolute":
        contents["/escape.py"] = b"bad"
    elif attack == "collision":
        contents["generated-1.0.data/purelib/generated.py"] = b"collision"
    elif attack == "second_metadata":
        contents["other-1.0.dist-info/METADATA"] = b"Name: other\nVersion: 1.0\n"
    else:
        contents["generated-1.0.dist-info/METADATA"] = b"Name: other\nVersion: 1.0\n"
    repack_wheel(tmp_path, contents)
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize("attack", ["duplicate", "symlink"])
def test_locked_archive_rejects_duplicate_and_symlink_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, attack: str
) -> None:
    """No extraction or last-member-wins interpretation can lend source evidence to unsafe ZIPs."""
    write_python(tmp_path, monkeypatch)
    path = wheel_path(tmp_path)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with zipfile.ZipFile(path, "a") as wheel:
        if attack == "duplicate":
            with pytest.warns(UserWarning, match="Duplicate name"):
                wheel.writestr("generated.py", b"duplicate")
        else:
            member = zipfile.ZipInfo("symlink")
            member.external_attr = (stat.S_IFLNK | 0o777) << 16
            wheel.writestr(member, "generated.py")
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    lock = tmp_path / "uv.lock"
    lock.write_text(lock.read_text().replace(before, after))
    assert python_inventory(tmp_path, monkeypatch).findings


@pytest.mark.parametrize("changed", [False, True])
def test_installer_bytecode_must_match_compilation_of_verified_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, changed: bool
) -> None:
    """Generated bytecode is allowed only when it matches trusted wheel source without execution."""
    write_python(tmp_path, monkeypatch)
    source = tmp_path / "site/generated.py"
    py_compile.compile(str(source), doraise=True)
    bytecode = Path(importlib.util.cache_from_source(str(source)))
    if changed:
        bytecode.write_bytes(bytecode.read_bytes()[:16] + b"injected")
    write_record(tmp_path / "site")
    assert bool(python_inventory(tmp_path, monkeypatch).findings) == changed


@pytest.mark.parametrize("address", ["", "http://example.org/generated/source"])
def test_verified_wheel_without_https_source_still_produces_finding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, address: str
) -> None:
    """Even fully matching wheel bytes cannot waive the separate HTTPS source requirement."""
    write_python(tmp_path, monkeypatch)
    contents = wheel_contents(tmp_path)
    metadata = "generated-1.0.dist-info/METADATA"
    value = contents[metadata].decode().split("Project-URL:")[0]
    if address:
        value += f"Project-URL: Source, {address}\n"
    contents[metadata] = value.encode()
    repack_wheel(tmp_path, contents)
    (tmp_path / "site" / metadata).write_text(value)
    write_record(tmp_path / "site")
    report = python_inventory(tmp_path, monkeypatch)
    evidence = report.packages[0].mpl
    assert evidence is not None
    assert not evidence.failure
    assert evidence.integrity
    assert report.findings
