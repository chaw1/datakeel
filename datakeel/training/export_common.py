# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Safe filenames, decoded dimensions and deterministic training archive packaging."""

import gzip
import hashlib
import json
import shutil
import tarfile
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from datakeel.core.errors import ConflictError, ValidationError
from datakeel.core.training_export_models import TrainingExportItem
from datakeel.training.importers import validate_box

_MAX_SUFFIX_LENGTH = 12
_MAX_CLASS_BYTES = 200


def json_text(value: object) -> str:
    """Serialize portable JSON without volatile formatting or non-finite numbers."""
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )


def filename(item: TrainingExportItem) -> str:
    """Derive a traversal-free collision-resistant basename from the stable source identity."""
    suffix = Path(item.file.filename).suffix.lower()
    if not suffix or len(suffix) > _MAX_SUFFIX_LENGTH or not suffix[1:].isalnum():
        suffix = ".bin"
    return hashlib.sha256(item.file.id.encode()).hexdigest() + suffix


def class_directory(category: str) -> str:
    """Keep ordinary class names readable while encoding unsafe path components."""
    if category in {"", ".", ".."}:
        return "class-" + hashlib.sha256(category.encode()).hexdigest()
    encoded = "".join(
        character if character.isalnum() or character in " _-." else quote(character, safe="")
        for character in category
    )
    if len(encoded.encode()) > _MAX_CLASS_BYTES:
        encoded = encoded[:32] + "-" + hashlib.sha256(category.encode()).hexdigest()
    return encoded


def copy_source(item: TrainingExportItem, destination: Path) -> None:
    """Copy the materialized version bytes and refuse any stale or modified source."""
    source = Path(item.file.path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    with destination.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    if checksum != item.file.sha256 or destination.stat().st_size != item.file.size:
        message = "Source content differs from the frozen dataset version; export refused"
        raise ConflictError(message)


def dimensions(item: TrainingExportItem) -> tuple[int, int]:
    """Read actual image dimensions and validate every detection against those pixels."""
    with Image.open(item.file.path) as image:
        width, height = image.size
    annotation = item.annotation
    if (annotation.image_width is not None and annotation.image_width != width) or (
        annotation.image_height is not None and annotation.image_height != height
    ):
        message = "Annotation dimensions differ from source image dimensions"
        raise ValidationError(message)
    for box in annotation.boxes or ():
        validate_box(box, width, height)
    return width, height


def write_archive(directory: Path, output: Path) -> None:
    """Create byte-stable tar or gzip tar with neutral host metadata and gzip headers."""
    with output.open("wb") as raw, ExitStack() as stack:
        sink = (
            stack.enter_context(gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0))
            if output.name.endswith((".tar.gz", ".tgz"))
            else raw
        )
        stream = stack.enter_context(
            tarfile.open(fileobj=sink, mode="w", format=tarfile.PAX_FORMAT)
        )
        for path in sorted(directory.rglob("*")):
            member = stream.gettarinfo(str(path), arcname=path.relative_to(directory).as_posix())
            member.uid = member.gid = member.mtime = 0
            member.uname = member.gname = ""
            member.mode = 0o755 if path.is_dir() else 0o644
            if path.is_file():
                with path.open("rb") as content:
                    stream.addfile(member, content)
            else:
                stream.addfile(member)
