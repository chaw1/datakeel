# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require an actionable failure when Rust is absent from the development environment."""

import shutil
import subprocess
from pathlib import Path


def test_rust_gate_without_cargo_fails_with_installation_instructions(tmp_path: Path) -> None:
    """A missing toolchain must fail before attempting Python or extension commands."""
    make = shutil.which("make")
    assert make is not None
    result = subprocess.run(  # noqa: S603  # Fixed local Makefile target; isolated empty PATH.
        [make, "-f", str(Path(__file__).resolve().parents[1] / "Makefile"), "check-rust"],
        cwd=tmp_path,
        env={"PATH": str(tmp_path), "HOME": str(tmp_path), "LANG": "C"},
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode != 0
    assert "Rust toolchain required" in result.stdout
    assert "https://rustup.rs/" in result.stdout
