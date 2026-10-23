# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Deterministic, entirely generated demonstration inputs."""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


def generate_samples(directory: Path) -> list[Path]:
    """Generate two hundred local images and two hundred text samples."""
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(200):
        path = directory / f"scene-{index:03d}.png"
        rng = np.random.default_rng(index)
        image = Image.fromarray(rng.integers(40, 210, (128, 192, 3), dtype=np.uint8))
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((20, 20, 100, 100), fill=(index % 255, 120, 220))
        drawing.text((35, 60), f"{index:03d}", fill=(255, 255, 255))
        image.save(path)
        paths.append(path)
    topics = ("forest", "coast", "mountain", "meadow")
    for index in range(200):
        path = directory / f"note-{index:03d}.txt"
        text = (
            f"Observation {index:03d}: a {topics[index % 4]} scene in a generated benchmark. "
            f"The measured sample index is {index * 37}. "
            f"Contact sample-{index}@users.noreply.github.com.\n"
        )
        if index in (198, 199):
            text = ""
        path.write_text(text, encoding="utf-8")
        paths.append(path)
    return paths
