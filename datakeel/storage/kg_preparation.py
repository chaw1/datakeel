# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Read immutable text inputs and freeze the complete consent boundary synchronously."""

import hashlib
from pathlib import Path

import yaml
from pydantic import ValidationError as ModelValidationError
from sqlalchemy.orm import Session

from datakeel.actions.kg_parameters import RunKGExtractionParams
from datakeel.actions.parameters import selection_for
from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.errors import NotFoundError, ValidationError
from datakeel.core.harness_pricing import nanos_to_usd, reservation_cost
from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
from datakeel.core.kg_execution import KGDocument, KGDocumentFingerprint, KGEstimate, KGPrepared
from datakeel.core.kg_models import Recording
from datakeel.core.models import AssetRef, FileItem
from datakeel.core.transcription_models import TranscriptionProfile
from datakeel.kg.loader import contracts_path, get_profile, get_schema
from datakeel.kg.policy import is_external, target_host
from datakeel.kg.prompt import document_profile, extraction_prompt
from datakeel.kg.text import chunk_text, decode_text
from datakeel.storage.database import DatasetRow, VersionRow
from datakeel.storage.datasets import materialize_files
from datakeel.storage.evidence_import import IMAGE_SUFFIXES
from datakeel.storage.kg_image_preparation import image_document, prepare_images
from datakeel.storage.kg_pricing import metering_config
from datakeel.storage.object_queries import evaluate_in_session
from datakeel.transcription.loader import get_profile as get_transcription_profile
from datakeel.transcription.loader import read_recording as read_transcription_recording


def _document(file: FileItem, version_id: str, profile: ExtractionProfile) -> KGDocument:
    content = Path(file.path).read_bytes()
    revision = hashlib.sha256(content).hexdigest()
    if file.sha256 and file.sha256 != revision:
        msg = "Graph source content no longer matches its immutable manifest"
        raise ValidationError(msg)
    try:
        text = decode_text(content)
    except UnicodeDecodeError as error:
        msg = f"Graph source is not UTF-8 text: {file.filename}"
        raise ValidationError(msg) from error
    if "\0" in text:
        msg = f"Graph source contains binary content: {file.filename}"
        raise ValidationError(msg)
    return KGDocument(
        asset_ref=AssetRef(
            asset_type="file", asset_id=file.id, version=version_id, display_name=file.filename
        ),
        filename=file.filename,
        text=text,
        content_revision=revision,
        blocks=chunk_text(text, profile.chunk_size, profile.chunk_overlap),
    )


def read_documents(
    session: Session,
    params: RunKGExtractionParams,
    profile: ExtractionProfile,
    transcription_profile: TranscriptionProfile | None = None,
) -> tuple[KGDocument, ...]:
    """Decode the exact selected immutable manifest without exposing storage rows."""
    version = session.get(VersionRow, params.version_id)
    if version is None or version.dataset_id != params.dataset_id:
        msg = "Graph input version does not belong to the selected dataset"
        raise NotFoundError(msg)
    manifest = evaluate_in_session(session, selection_for(params))
    identifiers = {item.asset_ref.asset_id for item in manifest.objects}
    if manifest.truncated or (params.file_ids and identifiers != set(params.file_ids)):
        msg = "Graph file selection is incomplete or unavailable"
        raise ValidationError(msg)
    files = [FileItem.model_validate(value) for value in version.manifest]
    selected = [item for item in files if item.id in identifiers]
    if not selected:
        msg = "Graph extraction requires at least one source document"
        raise ValidationError(msg)
    transcription = transcription_profile
    if transcription is None and any(
        Path(file.filename).suffix.lower() in IMAGE_SUFFIXES for file in selected
    ):
        transcription = get_transcription_profile(params.transcription_profile_id)
    recording_hash = read_transcription_recording(transcription)[0] if transcription else None
    result: list[KGDocument] = []
    for file in materialize_files(selected):
        if Path(file.filename).suffix.lower() in IMAGE_SUFFIXES and transcription:
            mode = params.mode_overrides.get(file.id, transcription.mode)
            result.append(
                image_document(
                    file,
                    transcription,
                    recording_hash,
                    mode,
                )
            )
        else:
            result.append(_document(file, version.id, profile))
    image_ids = {document.asset_ref.asset_id for document in result if document.image}
    if set(params.mode_overrides) - image_ids:
        msg = "Transcription mode overrides must refer to selected image file IDs"
        raise ValidationError(msg)
    return tuple(result)


def read_recording(profile: ExtractionProfile) -> tuple[str | None, Recording | None]:
    """Read and hash a validated recording without leaking parser source fragments."""
    if not profile.recording:
        return None, None
    path = Path(profile.recording)
    path = path if path.is_absolute() else contracts_path() / path
    try:
        content = path.read_bytes()
        recording = Recording.model_validate(yaml.safe_load(content))
    except (OSError, yaml.YAMLError, ModelValidationError) as error:
        msg = "Graph recording could not be read or validated"
        raise ValidationError(msg) from error
    return hashlib.sha256(content).hexdigest(), recording


def _prepared(
    documents: tuple[KGDocument, ...], schema: KGSchema, profile: ExtractionProfile
) -> KGPrepared:
    config = metering_config(profile, "prepare")
    blocks = tuple(block for document in documents for block in document.blocks)
    tokens = sum(
        estimate_tokens(extraction_prompt(block, schema, profile.prompt_version))
        for block in blocks
    )
    cost = nanos_to_usd(
        reservation_cost(config.price, tokens, len(blocks) * profile.max_output_tokens)
    )
    recording_hash, _ = read_recording(profile)
    return KGPrepared(
        schema_definition=schema,
        profile=profile,
        documents=tuple(KGDocumentFingerprint.from_document(document) for document in documents),
        estimate=KGEstimate(
            target_host=target_host(profile),
            model=profile.model,
            documents=len(documents),
            blocks=len(blocks),
            input_tokens=tokens,
            max_output_tokens=profile.max_output_tokens,
            cost_upper_usd=cost if config.known_price else None,
            price_version=config.price_version if config.known_price else None,
            price=config.price if config.known_price else None,
        ),
        accounting_price=config.price,
        accounting_price_version=config.price_version,
        recording_hash=recording_hash,
        external=is_external(profile),
    )


def prepare_kg_params(session: Session, params: RunKGExtractionParams) -> RunKGExtractionParams:
    """Recompute every supplied snapshot before it enters a signed plan digest."""
    profile, schema = get_profile(params.profile_id), get_schema(params.schema_id)
    profile = document_profile(profile, image=False)
    documents = read_documents(session, params, profile)
    prepared = _prepared(documents, schema, profile)
    if any(document.image is not None for document in documents):
        prepared = prepare_images(
            prepared, documents, get_transcription_profile(params.transcription_profile_id)
        )
    dataset = session.get(DatasetRow, params.dataset_id)
    prepared = prepared.model_copy(
        update={"handwriting": bool(dataset and dataset.metadata_values.get("handwriting") is True)}
    )
    return params.model_copy(update={"prepared": prepared})
