# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build and require the real isolated runtime; missing Docker is a test failure."""

import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from datakeel.core.settings import Settings
from datakeel.operators.custom_process import RuntimeFailureError, command, runtime_environment


@pytest.fixture(scope="session")
def sandbox_settings() -> Settings:
    """Require a locally built immutable sandbox image without skipping any security test."""
    executable = shutil.which("docker")
    if executable is None:
        pytest.fail(
            "Sandbox security tests require a Docker-compatible runtime; no tests were skipped"
        )
    settings = Settings()
    environment = runtime_environment(settings.sandbox_docker_host)
    root = Path(__file__).resolve().parents[3]
    image_name = "datakeel-sandbox-tests-" + uuid4().hex
    try:
        built = command(
            [
                executable,
                "build",
                "-f",
                str(root / "sandbox/Dockerfile"),
                "-t",
                image_name,
                str(root),
            ],
            environment,
            timeout=180,
            maximum=2 * 1024 * 1024,
        )
        if built.code:
            pytest.fail(
                "Sandbox image build failed: " + built.stderr.decode(errors="replace")[-2000:]
            )
        image = command(
            [executable, "image", "inspect", image_name, "--format", "{{.Id}}"],
            environment,
        )
    except RuntimeFailureError as error:
        pytest.fail("Sandbox security tests require a working container runtime: " + str(error))
    return settings.model_copy(
        update={"sandbox_image": image.stdout.decode().strip(), "sandbox_backend": "container"}
    )
