# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build one local-only Datakeel image; publication is deliberately unsupported."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

ROOT = Path(__file__).resolve().parents[1]


def docker_build_command() -> list[str]:
    """Return the complete local build argv, with no push or remote-tag option."""
    return [
        "docker",
        "build",
        "--file",
        "Dockerfile",
        "--tag",
        "datakeel:local",
        ".",
    ]


def main() -> None:
    """Build the local image from the wheel and locked requirements in dist/."""
    subprocess.run(  # noqa: S603  # Docker is the required local build tool; no shell.
        docker_build_command(), cwd=ROOT, check=True, timeout=1800
    )
    Console().print("Built local image datakeel:local (not pushed)")


if __name__ == "__main__":
    main()
