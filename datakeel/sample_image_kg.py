# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Copy attributed image samples byte-for-byte and label the scripted failure separately."""

import shutil
from pathlib import Path

from datakeel.core.models import BoundaryModel
from datakeel.kg.loader import contracts_path

IMAGE_DEMO_NAMES = (
    "zh01_clean.png",
    "zh01_scan.jpg",
    "en12_clean.png",
    "en01_scan.jpg",
    "b01.png",
    "b03.png",
    "b04.png",
    "b07.png",
    "b09.png",
    "b12.png",
)


class ImageKGSampleFiles(BoundaryModel):
    """Separate recorded images from an explicitly scripted truncation illustration."""

    recorded: tuple[Path, ...]
    truncated: Path

    @property
    def paths(self) -> tuple[Path, ...]:
        """Return the complete stable demonstration import selection."""
        return (*self.recorded, self.truncated)


def generate_image_kg_samples(directory: Path) -> ImageKGSampleFiles:
    """Preserve source content hashes for deterministic offline replay."""
    directory.mkdir(parents=True, exist_ok=True)
    root = contracts_path()
    recorded = tuple(
        Path(shutil.copyfile(root / "eval/image/images" / name, directory / name))
        for name in IMAGE_DEMO_NAMES
    )
    truncated = directory / "scripted-transcription-truncated.png"
    shutil.copyfile(root / "demo/image-truncated.png", truncated)
    return ImageKGSampleFiles(recorded=recorded, truncated=truncated)
