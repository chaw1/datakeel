# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build and inspect one local wheel without any publication entry point."""

from __future__ import annotations

import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

from rich.console import Console

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from scripts.public_scan import _scan_blob

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_WHEEL_FILES = frozenset(
    {
        "datakeel/cli/__init__.py",
        "datakeel/_contracts/model-prices.yaml",
        "datakeel/web_dist/index.html",
        "datakeel/web_dist/THIRD-PARTY-LICENSES.txt",
        "datakeel/THIRD_PARTY_NOTICES.md",
    }
)


class WheelReport(BoundaryModel):
    """Describe one verified local artifact without exposing scanned content."""

    filename: str
    size_bytes: int
    sha256: str
    file_count: int


def validate_wheel(path: Path) -> WheelReport:
    """Require runtime resources, notices, and a clean public-content scan."""
    if not path.name.startswith("datakeel-") or not path.name.endswith("-py3-none-any.whl"):
        msg = "Expected one pure Python datakeel wheel"
        raise ValidationError(msg)
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        missing = sorted(REQUIRED_WHEEL_FILES - names)
        license_name = next(
            (name for name in names if name.endswith(".dist-info/licenses/LICENSE")), None
        )
        if license_name is None:
            missing.append("dist-info/licenses/LICENSE")
        if missing:
            msg = "Wheel is missing required files: " + ", ".join(missing)
            raise ValidationError(msg)
        notices = archive.read("datakeel/THIRD_PARTY_NOTICES.md")
        for package in (b"opentelemetry-sdk", b"opentelemetry-exporter-otlp-proto-http"):
            if package not in notices:
                msg = f"Wheel notices are stale: missing {package.decode()}"
                raise ValidationError(msg)
        for info in archive.infolist():
            if info.is_dir():
                continue
            result = _scan_blob(info.filename, archive.read(info), ())
            if result.findings:
                rules = ", ".join(sorted({item.rule for item in result.findings}))
                msg = f"Wheel public scan failed for {info.filename}: {rules}"
                raise ValidationError(msg)
    return WheelReport(
        filename=path.name,
        size_bytes=path.stat().st_size,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        file_count=len(names),
    )


def _run(arguments: list[str]) -> None:
    subprocess.run(  # noqa: S603  # Fixed maintainer commands; never a shell.
        arguments, cwd=ROOT, check=True, capture_output=True, text=True, timeout=600
    )


def main() -> None:
    """Refresh notices, build one wheel, export locked dependencies, and validate it."""
    dist = ROOT / "dist"
    dist.mkdir(exist_ok=True)
    for old in dist.glob("datakeel-*.whl"):
        old.unlink()
    _run(["npm", "--prefix", "web", "ci"])
    _run([sys.executable, str(ROOT / "scripts" / "license_audit.py")])
    _run(["uv", "build", "--wheel"])
    requirements = dist / "requirements.txt"
    _run(
        [
            "uv",
            "export",
            "--locked",
            "--no-dev",
            "--no-emit-project",
            "--format",
            "requirements-txt",
            "--output-file",
            str(requirements),
        ]
    )
    if "--hash=" not in requirements.read_text(encoding="utf-8"):
        msg = "Locked Docker requirements must include hashes"
        raise ValidationError(msg)
    wheels = list(dist.glob("datakeel-*.whl"))
    if len(wheels) != 1:
        msg = f"Expected exactly one wheel, found {len(wheels)}"
        raise ValidationError(msg)
    report = validate_wheel(wheels[0])
    Console().print(f"Built {report.filename}: {report.size_bytes} bytes, sha256={report.sha256}")


if __name__ == "__main__":
    main()
