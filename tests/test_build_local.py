# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local wheel/image build contracts never invoke a publication channel."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from datakeel.core.errors import ValidationError
from scripts import build_image, build_wheel
from scripts.license_base import validate_base_inventory
from scripts.license_python import python_packages

ROOT = Path(__file__).resolve().parents[1]


def wheel(path: Path, *, notices: bool = True) -> None:
    """Create a minimal valid wheel containing all required public resources."""
    files = {
        name: b"generated safe content\n"
        for name in build_wheel.REQUIRED_WHEEL_FILES
        if notices or "THIRD_PARTY_NOTICES.md" not in name
    }
    if notices:
        files["datakeel/THIRD_PARTY_NOTICES.md"] = (
            b"opentelemetry-sdk\nopentelemetry-exporter-otlp-proto-http\n"
        )
    files["datakeel-0.22.0.dist-info/licenses/LICENSE"] = b"Apache-2.0\n"
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)


def validation_failed(path: Path) -> bool:
    """Return only an expected validation outcome, leaving other errors unhandled."""
    try:
        build_wheel.validate_wheel(path)
    except ValidationError:
        return True
    return False


def test_wheel_validation_when_complete_reports_artifact_identity(tmp_path: Path) -> None:
    """A pure wheel with resources and current notices passes content inspection."""
    path = tmp_path / "datakeel-0.22.0-py3-none-any.whl"
    wheel(path)
    report = build_wheel.validate_wheel(path)
    assert report.filename == path.name
    assert len(report.sha256) == 64
    assert report.file_count == len(build_wheel.REQUIRED_WHEEL_FILES) + 1


def test_wheel_validation_when_notices_missing_fails(tmp_path: Path) -> None:
    """Removing the required notices guard makes this test fail under mutation."""
    path = tmp_path / "datakeel-0.22.0-py3-none-any.whl"
    wheel(path, notices=False)
    assert validation_failed(path)


def test_wheel_validation_when_notices_stale_fails(tmp_path: Path) -> None:
    """A wheel cannot rely on an earlier license-audit run."""
    path = tmp_path / "datakeel-0.22.0-py3-none-any.whl"
    wheel(path)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr("datakeel/THIRD_PARTY_NOTICES.md", "stale\n")
    assert validation_failed(path)


def test_docker_build_command_when_called_is_local_build_only() -> None:
    """The complete argv has no push, registry login, or remote image name."""
    assert build_image.docker_build_command() == [
        "docker",
        "build",
        "--file",
        "Dockerfile",
        "--tag",
        "datakeel:local",
        ".",
    ]


def test_dockerfile_when_read_uses_reviewed_base_nonroot_and_locked_two_step_install() -> None:
    """The application image shares the audited base and installs the same wheel separately."""
    dockerfile = (ROOT / "Dockerfile").read_text()
    sandbox = (ROOT / "sandbox/Dockerfile").read_text()
    base = next(line for line in sandbox.splitlines() if line.startswith("FROM "))
    assert base in dockerfile
    requirements = dockerfile.index("--require-hashes")
    wheel_install = dockerfile.index("--no-deps")
    user = dockerfile.index("USER 65532:65532")
    assert requirements < wheel_install < user
    assert "mkdir /data" in dockerfile
    assert "chown datakeel:datakeel /data" in dockerfile
    assert "push" not in dockerfile
    assert "ENTRYPOINT" in dockerfile


def test_dockerignore_when_read_whitelists_only_build_inputs_and_sandbox() -> None:
    """Local state, internal reports, and source metadata stay out of the image context."""
    lines = set((ROOT / ".dockerignore").read_text().splitlines())
    assert "**" in lines
    assert "!dist/datakeel-*.whl" in lines
    assert "!dist/requirements.txt" in lines
    assert "!datakeel/**/*.py" not in lines
    assert "!datakeel/sandbox_entry.py" in lines
    assert "!datakeel/sandbox_worker.py" in lines
    assert "!.git/" not in lines


def test_base_inventory_when_application_base_changes_fails(tmp_path: Path) -> None:
    """The existing base evidence covers the application only while its digest is identical."""
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    for name in ("Dockerfile", "BASE_IMAGE_INVENTORY.json"):
        (sandbox / name).write_bytes((ROOT / "sandbox" / name).read_bytes())
    (tmp_path / "Dockerfile").write_bytes((ROOT / "Dockerfile").read_bytes())
    audited = python_packages(ROOT)
    validate_base_inventory(tmp_path, audited)
    application = tmp_path / "Dockerfile"
    application.write_text(application.read_text().replace("sha256:", "sha256:0", 1))
    with pytest.raises(ValueError, match="Base license inventory"):
        validate_base_inventory(tmp_path, audited)


def test_protobuf_license_when_locked_uses_reviewed_bsd_evidence() -> None:
    """The installed locked protobuf distribution matches its declaration and LICENSE hash."""
    packages = {package.name: package for package in python_packages(ROOT)}
    assert packages["protobuf"].license == "BSD-3-Clause"
    assert (
        "6e5e117324afd944dcf67f36cf329843bc1a92229a8cd9bb573d7a83130fea7d"
        in packages["protobuf"].evidence
    )
