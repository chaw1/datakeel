# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""One definition of the pixels a task image shows in the workbench.

The workbench canvas, its thumbnails and cloud prelabel requests all read task images through
``workbench_image`` so model boxes land in the same coordinate system people annotate in.
Today that is the stored pixel order with EXIF orientation ignored (``task_content`` strips
the tag before serving); changing the orientation policy means changing only this function.
"""

from pathlib import Path

from PIL import Image


def workbench_image(path: Path) -> Image.Image:
    """Decode the task image in the workbench's coordinate system, detached from the file."""
    with Image.open(path) as source:
        source.load()
        return source.copy()
