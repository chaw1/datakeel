# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expand imported directories and read image headers before files are stored."""

from collections.abc import Iterator, Sequence
from pathlib import Path

from pydantic import JsonValue

from datakeel.storage.image_geometry import geometry_metadata, read_geometry


def import_sources(paths: Sequence[Path]) -> Iterator[tuple[Path, str | None]]:
    """Yield each file with its POSIX path relative to the directory it was imported from.

    A file named directly keeps no relative path. Inside a directory, hidden entries and
    symbolic links are skipped so the import never reaches outside the chosen root.
    """
    for path in paths:
        if not path.is_dir():
            yield path, None
            continue
        for item in sorted(path.rglob("*")):
            relative = item.relative_to(path)
            if (
                item.is_symlink()
                or not item.is_file()
                or any(part.startswith(".") for part in relative.parts)
            ):
                continue
            yield item, relative.as_posix()


def image_dimensions(path: Path) -> dict[str, JsonValue]:
    """Record upright width/height, stored width/height and EXIF orientation from the header.

    Unreadable images record unknown sizes; a missing or unreadable orientation counts as 1.
    """
    return geometry_metadata(read_geometry(path))
