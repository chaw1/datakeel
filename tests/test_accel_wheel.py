# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Distribution content scanning catches generated metadata outside the source worktree."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts.check_accel_wheel import inspect_wheel


def _wheel(
    root: Path, content: str | bytes, name: str = "fixture.dist-info/sboms/generated.json"
) -> Path:
    path = root / "fixture.whl"
    with ZipFile(path, "w") as archive:
        archive.writestr(name, content)
    return path


def test_public_metadata_and_native_binary_pass(tmp_path: Path) -> None:
    """Scan valid public text and avoid treating native object bytes as source metadata."""
    path = _wheel(tmp_path, '{"name": "fixture", "license": "Apache-2.0"}')
    with ZipFile(path, "a") as archive:
        archive.writestr("fixture/_native.abi3.so", b"\0\xff\xfe\x80native fixture")
    report = inspect_wheel(path)
    assert report.members == 2
    assert report.text_members == 1
    assert report.findings == ()


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ('{"path": "' + "/" + 'Users/private-owner/project"}', "local_path"),
        ('{"author": "fixture@' + 'private-person.net"}', "email"),
        ('{"server": "' + "192." + '168.7.9"}', "private_ip"),
    ],
)
def test_generated_metadata_rejects_private_content(tmp_path: Path, source: str, rule: str) -> None:
    """Generated SBOM fields are subject to the same rules as tracked public source."""
    report = inspect_wheel(_wheel(tmp_path, source))
    assert [finding.rule for finding in report.findings] == [rule]
    assert report.findings[0].member == "fixture.dist-info/sboms/generated.json"
    assert source not in report.model_dump_json()


def test_text_with_native_extension_is_still_scanned(tmp_path: Path) -> None:
    """A filename extension alone cannot exclude valid UTF-8 text from the gate."""
    source = "contact: fixture@" + "private-person.net"
    report = inspect_wheel(_wheel(tmp_path, source, "fixture/native.so"))
    assert report.findings[0].rule == "email"


def test_binary_data_with_null_bytes_is_not_text(tmp_path: Path) -> None:
    """NUL-delimited native data must not be mistaken for text metadata."""
    source = b"\0native\0object\0"
    report = inspect_wheel(_wheel(tmp_path, source, "fixture/native.so"))
    assert report.text_members == 0


@pytest.mark.parametrize(
    "source",
    [
        b"\0\xffnative\0/" + b"Users/fixture-owner/source.rs\0",
        b"\0native\0/" + b"home/fixture-owner/source.rs\0",
    ],
)
def test_native_binary_rejects_embedded_local_source_paths(tmp_path: Path, source: bytes) -> None:
    """Stripping debug symbols alone cannot permit leaked panic/source location strings."""
    report = inspect_wheel(_wheel(tmp_path, source, "fixture/native.so"))
    assert report.text_members == 0
    assert [finding.rule for finding in report.findings] == ["local_path"]
    assert "fixture-owner" not in report.model_dump_json()
