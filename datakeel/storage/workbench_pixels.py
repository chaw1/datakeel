# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One definition of the pixels a task image shows in the workbench.

Cloud prelabel requests and the AI pre-review's perceptual hashes read task images through
``workbench_image``. Like the canvas and thumbnails served by ``image_geometry.upright_bytes``,
it applies the EXIF Orientation to the pixels, so model boxes land in the same upright (display)
frame people annotate in and the drafts they become are recorded as display-frame revisions.
"""

from pathlib import Path

from PIL import Image, ImageOps


def workbench_image(path: Path) -> Image.Image:
    """Decode the task image upright, detached from the file."""
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source)
