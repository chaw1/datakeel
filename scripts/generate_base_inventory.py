# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reproduce license evidence from an already-local owned sandbox image without networking."""

import argparse
import re
import shutil
from pathlib import Path
from uuid import uuid4

from pydantic import Field

from datakeel.core.models import BoundaryModel
from datakeel.core.settings import Settings
from datakeel.operators.custom_process import command, runtime_environment
from scripts.license_base_models import BaseImageInventory, CollectedBaseInventory


class ImageIdentity(BoundaryModel):
    """Restrict collection to an existing image built under the reserved sandbox prefix."""

    tags: tuple[str, ...] = Field(min_length=1)
    architecture: str
    os: str
    digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def generate(root: Path, image: str) -> BaseImageInventory:
    """Read only installed image metadata through one owned, isolated disposable container."""
    executable = shutil.which("docker")
    if executable is None or not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        msg = "Provide an already-local sandbox image pinned by sha256"
        raise ValueError(msg)
    environment = runtime_environment(Settings().sandbox_docker_host)
    template = (
        '{"tags":{{json .RepoTags}},"architecture":"{{.Architecture}}",'
        '"os":"{{.Os}}","digest":"{{.Id}}"}'
    )
    inspected = command([executable, "image", "inspect", image, "--format", template], environment)
    identity = ImageIdentity.model_validate_json(inspected.stdout)
    if not any(tag.startswith("datakeel-sandbox-") for tag in identity.tags):
        msg = "Only an owned sandbox image may be inspected"
        raise ValueError(msg)
    collected = _collect(root, executable, image, environment)
    references = re.findall(r"^FROM (.+)$", (root / "sandbox/Dockerfile").read_text(), re.MULTILINE)
    return BaseImageInventory(
        **collected.model_dump(),
        base_reference=references[0],
        image_digest=identity.digest,
        platform=identity.os + "/" + identity.architecture,
        os_package_count=len(collected.os_packages),
    )


def _collect(
    root: Path, executable: str, image: str, environment: dict[str, str]
) -> CollectedBaseInventory:
    name = "datakeel-sandbox-inventory-" + uuid4().hex
    label = "datakeel.sandbox.owner=" + name
    source = (root / "scripts/license_base_collect.py").read_text()
    created = False
    try:
        result = command(
            [
                executable,
                "create",
                "--name",
                name,
                "--label",
                label,
                "--pull=never",
                "--network=none",
                "--read-only",
                "--user=65532:65532",
                "--cap-drop=ALL",
                "--security-opt=no-new-privileges:true",
                "--memory=256m",
                "--memory-swap=256m",
                "--cpus=1",
                "--pids-limit=16",
                "--log-driver=none",
                "--entrypoint=/usr/local/bin/python",
                image,
                "-I",
                "-c",
                source,
            ],
            environment,
        )
        if result.code:
            msg = "The isolated image inventory container could not be created"
            raise ValueError(msg)
        created = True
        result = command(
            [executable, "start", "--attach", name], environment, timeout=30, maximum=2097152
        )
        if result.code:
            msg = (
                "Installed image dependency license evidence is incomplete: "
                + result.stderr.decode()
            )
            raise ValueError(msg)
        return CollectedBaseInventory.model_validate_json(result.stdout)
    finally:
        if created:
            _cleanup(executable, name, environment)


def _cleanup(executable: str, name: str, environment: dict[str, str]) -> None:
    owned = command(
        [
            executable,
            "inspect",
            "--format",
            '{{index .Config.Labels "datakeel.sandbox.owner"}}',
            name,
        ],
        environment,
    )
    if not owned.code and owned.stdout.decode().strip() == name:
        command([executable, "rm", "--force", name], environment)


def main() -> None:
    """Write a reproducible public inventory, excluding task logs and host identities."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    inventory = generate(args.root, args.image)
    destination = args.output or args.root / "sandbox/BASE_IMAGE_INVENTORY.json"
    destination.write_text(inventory.model_dump_json(indent=2) + "\n")


if __name__ == "__main__":
    main()
