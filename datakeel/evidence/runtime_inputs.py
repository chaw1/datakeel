# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve immutable sidecars and hash the actual inputs of each extractor."""

import hashlib
import json
from pathlib import Path

from pydantic import JsonValue

from datakeel.core.evidence_cache import EvidenceCacheEntry, EvidenceCacheKey, EvidenceInput
from datakeel.core.evidence_inputs import SampleSidecars, sample_sidecars
from datakeel.core.evidence_models import ExtractorRef
from datakeel.core.models import AssetRef, BoundaryModel, FileItem, JsonDocument
from datakeel.operators.evidence.contracts import contract_hashes
from datakeel.storage.datasets import materialize_files
from datakeel.storage.objects import digest


class PreparedInputs(BoundaryModel):
    """Bind materialized file facts and cache keys to one node's input snapshot."""

    files: list[FileItem]
    requests: tuple[EvidenceCacheEntry, ...]


def prepare_node_inputs(
    files: list[FileItem], version_id: str, extractor: ExtractorRef, params: JsonDocument
) -> PreparedInputs:
    """Hash each actual path once for both anchors and keys within this execution."""
    revisions: dict[str, str] = {}
    prepared = _prepare_inputs(files, version_id, revisions)
    return PreparedInputs(
        files=prepared, requests=_cache_requests(prepared, extractor, params, revisions)
    )


def subject_ref(file: FileItem) -> AssetRef:
    """Read the versioned source identity supplied by the worker context."""
    return AssetRef.model_validate(file.metadata["evidence_subject"])


def _revision(path: str, revisions: dict[str, str]) -> str:
    if path not in revisions:
        revisions[path] = digest(Path(path))
    return revisions[path]


def prepare_inputs(files: list[FileItem], version_id: str) -> list[FileItem]:
    """Materialize every sidecar from stored bytes and attach a source manifest identity."""
    return _prepare_inputs(files, version_id, {})


def _prepare_inputs(
    files: list[FileItem], version_id: str, revisions: dict[str, str]
) -> list[FileItem]:
    result: list[FileItem] = []
    sources = [sample_sidecars(file) for file in files]
    sidecar_files = iter(
        materialize_files(
            [
                sidecar
                for source in sources
                for sidecar in (source.caption, source.annotation)
                if sidecar is not None
            ]
        )
    )
    for file, source in zip(files, sources, strict=True):
        updated: dict[str, FileItem | None] = {}
        for field, sidecar in (("caption", source.caption), ("annotation", source.annotation)):
            materialized = next(sidecar_files) if sidecar is not None else None
            updated[field] = (
                materialized.model_copy(update={"sha256": _revision(materialized.path, revisions)})
                if materialized is not None
                else None
            )
        sidecars = source.model_copy(update=updated)
        subject = AssetRef(asset_type="file", asset_id=file.id, version=version_id)
        result.append(
            file.model_copy(
                update={
                    "sha256": _revision(file.path, revisions),
                    "metadata": {
                        **file.metadata,
                        "evidence_subject": subject.model_dump(mode="json"),
                        "evidence_sample": sidecars.model_dump(mode="json"),
                        "evidence_drafts": [],
                        "evidence_failed": False,
                    },
                }
            )
        )
    return result


def json_revision(value: JsonValue) -> str:
    """Hash normalized factual inputs while excluding paths and unrelated metadata."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _content(file: FileItem | None, role: str, revisions: dict[str, str]) -> EvidenceInput:
    revision = (
        _revision(file.path, revisions) if file is not None else json_revision({"missing": role})
    )
    return EvidenceInput(role=role, content_revision=revision)


def _sample_inputs(
    file: FileItem, operator: str, revisions: dict[str, str]
) -> tuple[EvidenceInput, ...]:
    sidecars: SampleSidecars = sample_sidecars(file)
    if operator == "evidence.caption_mentions":
        return (_content(sidecars.caption, "caption", revisions),)
    if operator == "evidence.image_phash":
        return (_content(file, "image", revisions),)
    values = (
        _content(file, "image", revisions),
        _content(sidecars.annotation, "annotation", revisions),
    )
    if operator == "evidence.label_gap":
        facts = JsonDocument.model_validate(
            {
                key: file.metadata.get(key)
                for key in (
                    "caption_mentions",
                    "caption_available",
                    "annotation_categories",
                    "annotation_available",
                )
            }
        )
        return (
            *values,
            _content(sidecars.caption, "caption", revisions),
            EvidenceInput(
                role="normalized_facts",
                content_revision=json_revision(facts.root),
            ),
        )
    return values


def cache_requests(
    files: list[FileItem], extractor: ExtractorRef, params: JsonDocument
) -> tuple[EvidenceCacheEntry, ...]:
    """Build versioned slots from complete source, parameter, and contract content."""
    return _cache_requests(files, extractor, params, {})


def _cache_requests(
    files: list[FileItem],
    extractor: ExtractorRef,
    params: JsonDocument,
    revisions: dict[str, str],
) -> tuple[EvidenceCacheEntry, ...]:
    lexicon_hash, near_duplicate_hash = contract_hashes()
    parameters = EvidenceInput(role="parameters", content_revision=json_revision(params.root))
    global_inputs = (
        (
            EvidenceInput(
                role="all_image_inputs",
                content_revision=json_revision(
                    [
                        {
                            "asset_id": file.id,
                            "content": _revision(file.path, revisions),
                            "phash": file.metadata.get("image_phash"),
                        }
                        for file in sorted(files, key=lambda item: item.id)
                    ]
                ),
            ),
        )
        if extractor.id == "evidence.near_duplicate"
        else ()
    )
    return tuple(
        EvidenceCacheEntry(
            subject=subject_ref(file),
            assertion_ids=(),
            key=EvidenceCacheKey(
                inputs=(*global_inputs, parameters)
                if global_inputs
                else (
                    *_sample_inputs(file, extractor.id, revisions),
                    parameters,
                ),
                extractor=extractor,
                lexicon_hash=lexicon_hash,
                near_duplicate_hash=near_duplicate_hash,
            ),
        )
        for file in files
    )
