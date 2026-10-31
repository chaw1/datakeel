# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve version-pinned task images through the object store for server-side model work."""

from functools import lru_cache
from pathlib import Path

from PIL import Image
from sqlalchemy.orm import Session

from datakeel.core.models import FileItem
from datakeel.core.production_models import Project
from datakeel.operators.evidence.image_phash import dhash
from datakeel.storage.database import VersionRow
from datakeel.storage.objects import object_store
from datakeel.storage.workbench_pixels import workbench_image


def sample_keys(session: Session, project: Project) -> dict[str, str]:
    """Map each pinned sample to its object key, from the project's immutable manifest."""
    version = session.get(VersionRow, project.version_id)
    if version is None or version.dataset_id != project.dataset_id:
        return {}
    keys: dict[str, str] = {}
    for item in version.manifest:
        file = FileItem.model_validate(item)
        key = file.metadata.get("object_key")
        if isinstance(key, str):
            keys[file.id] = key
    return keys


def sample_image(key: str) -> Image.Image:
    """Open the workbench pixels of one stored sample."""
    return workbench_image(Path(object_store().materialize(key)))


@lru_cache(maxsize=20000)
def sample_hash(key: str) -> int | None:
    """Cache the 64-bit dHash of immutable stored content; undecodable images have none."""
    try:
        with sample_image(key) as image:
            return int(dhash(image), 16)
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
