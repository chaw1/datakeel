# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve native manifest and execution identities to their owning dataset scope."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from datakeel.core.evidence_models import Assertion
from datakeel.core.models import AssetRef, FileItem
from datakeel.storage.ask_rows import AskAnswerRow
from datakeel.storage.database import DatasetRow, TaskRow, VersionRow
from datakeel.storage.evidence_rows import AssertionRow
from datakeel.storage.kg_rows import KGRunRow

_MANIFEST_IDS = "datakeel.asset_manifest_ids"


def native_targets(session: Session, ref: AssetRef) -> tuple[AssetRef, ...]:
    """Resolve files, versions, tasks, graph runs and assertions without content reads."""
    result: list[AssetRef] = []
    if ref.asset_type == "resource" and session.get(DatasetRow, ref.asset_id):
        result.append(AssetRef(asset_id=ref.asset_id, version=ref.version))
    result.extend(_version_targets(session, ref))
    if ref.asset_type in {"task", "resource"}:
        task = session.get(TaskRow, ref.asset_id)
        if task:
            result.append(AssetRef(asset_id=task.dataset_id, version=task.input_version_id))
    if ref.asset_type in {"kg_run", "resource"}:
        run = session.get(KGRunRow, ref.asset_id)
        if run:
            result.append(AssetRef(asset_id=run.dataset_id, version=run.version_id))
    result.extend(_evidence_targets(session, ref))
    if ref.asset_type in {"file", "artifact", "resource", "image_transcript", "text"}:
        result.extend(_file_targets(session, ref))
    return tuple(result)


def _version_dataset(session: Session, version_id: str) -> str | None:
    """Read a version's owning dataset without decoding its manifest."""
    return session.scalar(select(VersionRow.dataset_id).where(VersionRow.id == version_id))


def _version_targets(session: Session, ref: AssetRef) -> tuple[AssetRef, ...]:
    """Visit a pinned version's producer while retaining verified dataset ownership."""
    if ref.asset_type == "dataset" and ref.version is not None:
        owner = _version_dataset(session, ref.version)
        if owner == ref.asset_id:
            return (AssetRef(asset_type="version", asset_id=ref.version, version=ref.version),)
    if ref.asset_type in {"version", "resource"}:
        owner = _version_dataset(session, ref.asset_id)
        if owner is not None:
            return (AssetRef(asset_id=owner, version=ref.asset_id),)
    if ref.asset_type == "kg_entity" and ref.version is not None:
        # Graph entity identities carry the dataset version they were extracted from.
        owner = _version_dataset(session, ref.version)
        if owner is not None:
            return (AssetRef(asset_id=owner, version=ref.version),)
    return ()


def _manifest_ids(session: Session, version_id: str) -> frozenset[str]:
    """Read one immutable version manifest's file identities once per session.

    Listing a dataset resolves every file reference; decoding every manifest again for
    each file made that quadratic in files times versions.
    """
    cache: dict[str, frozenset[str]] = session.info.setdefault(_MANIFEST_IDS, {})
    ids = cache.get(version_id)
    if ids is None:
        manifest = session.scalar(select(VersionRow.manifest).where(VersionRow.id == version_id))
        ids = frozenset(FileItem.model_validate(raw).id for raw in manifest or [])
        cache[version_id] = ids
    return ids


def _file_targets(session: Session, ref: AssetRef) -> list[AssetRef]:
    # Image-region anchors pin a content revision rather than a version identity;
    # match such revisions conservatively, like an unversioned file read.
    pinned = ref.version is not None and _version_dataset(session, ref.version) is not None
    statement = select(VersionRow.id, VersionRow.dataset_id)
    if pinned:
        statement = statement.where(VersionRow.id == ref.version)
    result = [
        AssetRef(asset_id=dataset_id, version=version_id)
        for version_id, dataset_id in session.execute(statement)
        if ref.asset_id in _manifest_ids(session, version_id)
    ]
    if not result and not pinned:
        result.extend(
            AssetRef(asset_id=dataset.id)
            for dataset in session.scalars(select(DatasetRow))
            if any(FileItem.model_validate(raw).id == ref.asset_id for raw in dataset.files)
        )
    return result


def _evidence_targets(session: Session, ref: AssetRef) -> tuple[AssetRef, ...]:
    result: list[AssetRef] = []
    if ref.asset_type in {"question", "knowledge_bundle", "resource"}:
        answer = session.get(AskAnswerRow, ref.asset_id)
        if answer:
            result.append(AssetRef(asset_type="event", asset_id=answer.producer_event_id))
    if ref.asset_type in {"assertion", "resource"}:
        assertion = session.get(AssertionRow, ref.asset_id)
        if assertion:
            fact = Assertion.model_validate(assertion.payload)
            result.append(fact.subject)
            if isinstance(fact.object, AssetRef):
                result.append(fact.object)
            result.extend(anchor.asset_ref for anchor in fact.anchors)
    return tuple(result)
