# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build local immutable source identities independently of database imports."""

import hashlib
from pathlib import Path

from datakeel.core.evidence_drafts import ObservationDraft
from datakeel.core.evidence_inputs import SampleSidecars
from datakeel.core.models import AssetRef, FileItem
from datakeel.operators import REGISTRY


def local_file(path: Path, identifier: str, modality: str = "text") -> FileItem:
    """Describe local test bytes with a deterministic identity."""
    return FileItem(
        id=identifier,
        path=str(path),
        filename=path.name,
        modality=modality,
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        size=path.stat().st_size,
    )


def paired_file(directory: Path, relative: str) -> FileItem:
    """Attach independently addressable sidecars to a versioned source image."""
    path = directory / relative
    caption, annotation = path.with_name("caption.txt"), path.with_name("annotations.json")
    sidecars = SampleSidecars(
        sample_key=relative,
        split="train" if relative.startswith("train/") else "val",
        caption=local_file(caption, relative + ":caption") if caption.exists() else None,
        annotation=local_file(annotation, relative + ":annotation")
        if annotation.exists()
        else None,
    )
    return local_file(path, relative, "image").model_copy(
        update={
            "metadata": {
                "evidence_subject": AssetRef(
                    asset_type="file", asset_id=relative, version="v1"
                ).model_dump(),
                "evidence_sample": sidecars.model_dump(mode="json"),
                "split": sidecars.split,
            }
        }
    )


def run_node(name: str, file: FileItem, output: Path) -> FileItem:
    """Execute one registered evidence operator using its declared parameter schema."""
    return REGISTRY[f"evidence.{name}"].run([file], output).files[0]


def drafts(file: FileItem) -> list[ObservationDraft]:
    """Parse the current node's observation metadata back through its typed boundary."""
    return [ObservationDraft.model_validate(value) for value in file.metadata["evidence_drafts"]]
