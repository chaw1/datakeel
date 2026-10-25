# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Resolve frozen image and transcript assets without exposing mutable filesystem paths."""

from pathlib import Path
from urllib.parse import urlencode

from sqlalchemy import JSON, and_, exists, func, or_, select, type_coerce
from sqlalchemy.orm import Session

from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.evidence_models import Assertion
from datakeel.core.kg_execution import KGJob
from datakeel.core.kg_images import KGImageSource
from datakeel.core.kg_queries import KGSourceText
from datakeel.core.models import AssetRef
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import resolve_download
from datakeel.storage.kg_rows import KGRunRow
from datakeel.transcription.images import normalize_image


def _jobs(session: Session, extraction_id: str | None = None) -> tuple[KGJob, ...]:
    statement = select(KGRunRow).order_by(KGRunRow.created_at.desc(), KGRunRow.id)
    if extraction_id:
        statement = statement.where(KGRunRow.id == extraction_id)
    return tuple(KGJob.model_validate(row.payload) for row in session.scalars(statement))


def _source_jobs(
    session: Session, asset_id: str, version_id: str, extraction_id: str | None
) -> tuple[KGJob, ...]:
    # Filter in SQL so unrelated frozen documents are neither loaded nor validated.
    expand = (
        func.json_each if session.get_bind().dialect.name == "sqlite" else func.json_array_elements
    )
    documents = expand(KGRunRow.payload["documents"]).table_valued("value")
    document = type_coerce(documents.c.value, JSON)
    original = document["image"]["asset_ref"]
    transcript = document["asset_ref"]
    matching = exists(
        select(1)
        .select_from(documents)
        .where(
            document["image"]["asset_ref"]["asset_id"].as_string().is_not(None),
            or_(
                and_(
                    original["asset_id"].as_string() == asset_id,
                    original["version"].as_string() == version_id,
                ),
                and_(
                    transcript["asset_id"].as_string() == asset_id,
                    transcript["version"].as_string() == version_id,
                ),
            ),
        )
    )
    statement = select(KGRunRow).where(matching).order_by(KGRunRow.created_at.desc(), KGRunRow.id)
    if extraction_id:
        statement = statement.where(KGRunRow.id == extraction_id)
    return tuple(KGJob.model_validate(row.payload) for row in session.scalars(statement))


def _view(job: KGJob, image: KGImageSource, filename: str) -> KGSourceText:
    query = urlencode({"version_id": image.asset_ref.version, "extraction_id": job.run.id})
    return KGSourceText(
        asset_ref=image.asset_ref,
        filename=filename,
        text="",
        image_url=f"/api/kg/images/{image.asset_ref.asset_id}?{query}",
        width=image.width,
        height=image.height,
        transcriber=image.backend,
        transcription_model=image.model,
        transcription_profile_id=image.profile_id,
    )


def image_source(
    db: Database, asset_id: str, version_id: str, extraction_id: str | None = None
) -> KGSourceText | None:
    """Read exact transcript content or its corrected original image presentation."""
    with db.session() as session:
        for job in _source_jobs(session, asset_id, version_id, extraction_id):
            for document in job.documents:
                image = document.image
                if image is None:
                    continue
                if (image.asset_ref.asset_id, image.asset_ref.version) == (asset_id, version_id):
                    return _view(job, image, document.filename)
                if (document.asset_ref.asset_id, document.asset_ref.version) == (
                    asset_id,
                    version_id,
                ):
                    return KGSourceText(
                        asset_ref=document.asset_ref,
                        filename=document.filename,
                        text=document.text,
                        transcriber=image.backend,
                        transcription_model=image.model,
                        transcription_profile_id=image.profile_id,
                    )
    return None


def image_bytes(db: Database, asset_id: str, version_id: str, extraction_id: str) -> bytes:
    """Return metadata-free corrected pixels only when the requested content still matches."""
    with db.session() as session:
        jobs = _jobs(session, extraction_id)
    for job in jobs:
        for document in job.prepared.documents:
            image = document.image
            if image is None or (image.asset_ref.asset_id, image.asset_ref.version) != (
                asset_id,
                version_id,
            ):
                continue
            path = resolve_download(db, job.run.dataset_id, asset_id, job.run.version_id).path
            corrected = normalize_image(Path(path).read_bytes())
            if corrected.image_hash != image.content_revision:
                msg = "Image content no longer matches its evidence revision"
                raise ValidationError(msg)
            return corrected.png
    msg = "Knowledge-graph image was not found for the requested version"
    raise NotFoundError(msg)


def replaced_transcripts(session: Session, job: KGJob, touched: tuple[str, ...]) -> tuple[str, ...]:
    """Invalidate old derived assets when their original image completes re-extraction."""
    identifiers = set(touched)
    for previous in _jobs(session):
        if (previous.run.dataset_id, previous.run.version_id) != (
            job.run.dataset_id,
            job.run.version_id,
        ):
            continue
        identifiers.update(
            document.asset_ref.asset_id
            for document in previous.documents
            if document.image and document.image.asset_ref.asset_id in touched
        )
    return tuple(sorted(identifiers))


def image_review_references(session: Session, assertion: Assertion) -> list[AssetRef]:
    """Map derived text and pixel revisions back to immutable file-manifest review targets."""
    if not any(anchor.asset_ref.asset_type == "image_transcript" for anchor in assertion.anchors):
        return [anchor.asset_ref for anchor in assertion.anchors]
    origin = _jobs(session, assertion.run_id)
    if not origin:
        msg = "Image review extraction run is unavailable"
        raise ValidationError(msg)
    sources = _review_sources(session, origin[0])
    result: list[AssetRef] = []
    for anchor in assertion.anchors:
        key = (anchor.asset_ref.asset_id, anchor.asset_ref.version)
        found = sources.get(key)
        if found is not None:
            if found[1] != anchor.content_revision:
                msg = "Image review source revision does not match its saved transcript"
                raise ValidationError(msg)
            result.append(found[0])
        elif anchor.asset_ref.asset_type == "image_transcript":
            msg = "Image review transcript is unavailable"
            raise ValidationError(msg)
        else:
            result.append(anchor.asset_ref)
    return result


def _review_sources(
    session: Session, origin: KGJob
) -> dict[tuple[str, str | None], tuple[AssetRef, str]]:
    sources: dict[tuple[str, str | None], tuple[AssetRef, str]] = {}
    for job in _jobs(session):
        if (job.run.dataset_id, job.run.version_id) != (
            origin.run.dataset_id,
            origin.run.version_id,
        ):
            continue
        for document in job.documents:
            image = document.image
            if image is None:
                continue
            original = image.asset_ref.model_copy(update={"version": job.run.version_id})
            sources[(document.asset_ref.asset_id, document.asset_ref.version)] = (
                original,
                document.content_revision,
            )
            sources[(image.asset_ref.asset_id, image.asset_ref.version)] = (
                original,
                image.content_revision,
            )
    return sources
