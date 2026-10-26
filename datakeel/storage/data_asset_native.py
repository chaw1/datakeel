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


def _version_targets(session: Session, ref: AssetRef) -> tuple[AssetRef, ...]:
    """Visit a pinned version's producer while retaining verified dataset ownership."""
    if ref.asset_type == "dataset" and ref.version is not None:
        version = session.get(VersionRow, ref.version)
        if version is not None and version.dataset_id == ref.asset_id:
            return (AssetRef(asset_type="version", asset_id=version.id, version=version.id),)
    if ref.asset_type in {"version", "resource"}:
        row = session.get(VersionRow, ref.asset_id)
        if row:
            return (AssetRef(asset_id=row.dataset_id, version=row.id),)
    return ()


def _file_targets(session: Session, ref: AssetRef) -> list[AssetRef]:
    statement = select(VersionRow)
    if ref.version:
        statement = statement.where(VersionRow.id == ref.version)
    result = [
        AssetRef(asset_id=version.dataset_id, version=version.id)
        for version in session.scalars(statement)
        if any(FileItem.model_validate(raw).id == ref.asset_id for raw in version.manifest)
    ]
    if not result and ref.version is None:
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
