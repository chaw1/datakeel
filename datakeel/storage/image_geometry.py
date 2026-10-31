# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read and record upright image geometry; serve upright pixels without rewriting originals."""

import io
import warnings
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageOps
from pydantic import JsonValue

from datakeel.core.image_orientation import ORIENTATION_TAG, ImageGeometry, orientation_value
from datakeel.core.models import FileItem
from datakeel.storage.objects import object_store

_UNREADABLE = (OSError, ValueError, Image.DecompressionBombError)
_JPEG_MODES = frozenset({"L", "RGB", "CMYK"})


def read_geometry(path: Path) -> ImageGeometry | None:
    """Read stored size and EXIF orientation from the header only; None when unreadable."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                width, height = image.size
                orientation = orientation_value(image.getexif().get(ORIENTATION_TAG))
    except _UNREADABLE:
        return None
    if width <= 0 or height <= 0:
        return None
    return ImageGeometry(orientation=orientation, stored_width=width, stored_height=height)


def geometry_metadata(geometry: ImageGeometry | None) -> dict[str, JsonValue]:
    """Record upright width/height (the public size), stored size and orientation at import."""
    if geometry is None:
        return {
            "width": None,
            "height": None,
            "stored_width": None,
            "stored_height": None,
            "orientation": 1,
        }
    return {
        "width": geometry.width,
        "height": geometry.height,
        "stored_width": geometry.stored_width,
        "stored_height": geometry.stored_height,
        "orientation": geometry.orientation,
    }


def recorded_geometry(metadata: Mapping[str, JsonValue]) -> ImageGeometry | None:
    """Use geometry recorded at import; older manifests lack it and return None."""
    orientation = metadata.get("orientation")
    width, height = metadata.get("stored_width"), metadata.get("stored_height")
    if (
        not isinstance(orientation, int)
        or not isinstance(width, int)
        or not isinstance(height, int)
    ):
        return None
    if width <= 0 or height <= 0:
        return None
    return ImageGeometry(
        orientation=orientation_value(orientation), stored_width=width, stored_height=height
    )


@lru_cache(maxsize=65536)
def _object_geometry(key: str) -> ImageGeometry | None:
    # Object keys are content addressed, so a key's geometry never changes.
    return read_geometry(object_store().materialize(key))


def file_geometry(file: FileItem) -> ImageGeometry | None:
    """Resolve a stored file's upright geometry, backfilling older imports from the header."""
    if file.modality != "image":
        return None
    recorded = recorded_geometry(file.metadata)
    if recorded is not None:
        return recorded
    key = file.metadata.get("object_key")
    if isinstance(key, str) and key:
        return _object_geometry(key)
    path = Path(file.path) if file.path else None
    return read_geometry(path) if path is not None and path.is_file() else None


def legacy_geometry(file: FileItem) -> dict[str, JsonValue] | None:
    """Return the size fields an older image record lacks, read from its header.

    Imports up to v0.18.0 recorded the stored width/height and no orientation. Reads overlay
    the upright values; the immutable manifest is never rewritten. None means nothing to add.
    """
    if file.modality != "image" or recorded_geometry(file.metadata) is not None:
        return None
    geometry = file_geometry(file)
    return None if geometry is None else geometry_metadata(geometry)


class UprightImage(NamedTuple):
    """Re-encoded upright pixels and their media type."""

    content: bytes
    media_type: str


def upright_bytes(path: Path, *, thumbnail: int | None = None) -> UprightImage | None:
    """Encode upright pixels without EXIF orientation; None means the original is already upright.

    Full-size JPEG sources stay JPEG at quality 95 with 4:4:4 chroma (a quarter of a lossless
    PNG's bytes for a phone photo); every other format is lossless PNG. Thumbnails are JPEG
    and always re-encoded.
    """
    with Image.open(path) as image:
        orientation = orientation_value(image.getexif().get(ORIENTATION_TAG))
        if thumbnail is None and orientation == 1:
            return None
        source_format = image.format
        upright = ImageOps.exif_transpose(image)
        output = io.BytesIO()
        if thumbnail is not None:
            preview = upright.convert("RGB")
            preview.thumbnail((thumbnail, thumbnail))
            preview.save(output, "JPEG", quality=80)
            return UprightImage(output.getvalue(), "image/jpeg")
        if source_format == "JPEG" and upright.mode in _JPEG_MODES:
            upright.save(
                output,
                "JPEG",
                quality=95,
                subsampling=0,
                icc_profile=image.info.get("icc_profile"),
            )
            return UprightImage(output.getvalue(), "image/jpeg")
        upright.save(output, "PNG", icc_profile=image.info.get("icc_profile"))
        return UprightImage(output.getvalue(), "image/png")
