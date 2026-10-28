# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Run image cases through transcription, extraction and persisted production assertions."""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

from datakeel.core.errors import ValidationError
from datakeel.core.kg_errors import KGExtractionError
from datakeel.core.kg_eval_models import (
    KGBlockedRelation,
    KGEvalFailure,
    ScoredEntity,
    ScoredRecord,
)
from datakeel.core.kg_execution import KGDocument
from datakeel.core.kg_images import KGImageSource
from datakeel.core.kg_product import KGSource, ProductExtraction
from datakeel.core.models import AssetRef, BoundaryModel
from datakeel.core.transcription_errors import TranscriptionFailure, TranscriptionUnavailableError
from datakeel.core.transcription_models import TranscriptionResult
from datakeel.evidence.kg_images import enrich_image_product
from datakeel.kg.assembly import assemble_extraction
from datakeel.kg.cache import extraction_identity
from datakeel.kg.extractors import checked_extract
from datakeel.kg.text import chunk_text, decode_text
from datakeel.kg_eval.image_projection import image_predictions
from datakeel.kg_eval.projection import blocked_relations, raw_relations
from datakeel.storage.kg_image_eval_store import store_evaluation_product
from datakeel.storage.kg_image_preparation import transcript_ref
from datakeel.storage.kg_preparation import read_recording as read_extraction_recording
from datakeel.transcription.cache import profile_digest
from datakeel.transcription.images import normalize_image
from datakeel.transcription.loader import read_recording
from datakeel.transcription.quality import checked_transcribe

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.kg_contracts import ExtractionProfile, KGSchema
    from datakeel.core.kg_eval_models import ScoredRelation
    from datakeel.core.kg_image_eval import KGImageCase
    from datakeel.core.kg_models import ExtractionResult, TextBlock
    from datakeel.core.transcription_models import ImageInput, TranscriptionProfile
    from datakeel.kg.extractors import ExtractorAdapter
    from datakeel.storage.database import Database
    from datakeel.transcription.quality import TranscriberAdapter


class ImageCaseExecution(BoundaryModel):
    """Retain the measured transcript alongside independent and persisted candidate scores."""

    raw: ScoredRecord
    product: ScoredRecord
    blocked: tuple[KGBlockedRelation, ...]
    failures: tuple[KGEvalFailure, ...]
    transcript: TranscriptionResult


class ImageCaseRunner:
    """Reuse injected providers while persisting each case in an isolated evaluation database."""

    def __init__(
        self,
        db: Database,
        schema: KGSchema,
        profile: ExtractionProfile,
        transcription: TranscriptionProfile,
        extractor: ExtractorAdapter,
        transcriber: TranscriberAdapter,
    ) -> None:
        """Bind explicit providers without constructing or contacting any hidden backend."""
        self.db, self.schema, self.profile = db, schema, profile
        self.transcription, self.extractor, self.transcriber = transcription, extractor, transcriber
        self.digest = profile_digest(transcription, read_recording(transcription)[0])
        self.identity = extraction_identity(schema, profile, read_extraction_recording(profile)[0])

    def _document(
        self, case: KGImageCase, image: ImageInput, result: TranscriptionResult
    ) -> KGDocument:
        text = decode_text(result.text.encode())
        source = KGImageSource(
            asset_ref=AssetRef(asset_type="file", asset_id=case.id, version=image.image_hash),
            content_revision=image.image_hash,
            width=image.width,
            height=image.height,
            mode=result.mode,
            profile_id=self.transcription.id,
            profile_digest=self.digest,
            backend=result.backend,
            model=result.model,
            lines=result.lines,
        )
        ref = transcript_ref(source, text)
        return KGDocument(
            asset_ref=ref,
            filename=case.image,
            text=text,
            content_revision=hashlib.sha256(text.encode()).hexdigest(),
            blocks=chunk_text(text, self.profile.chunk_size, self.profile.chunk_overlap),
            image=source,
        )

    def _product(
        self, document: KGDocument, block: TextBlock, result: ExtractionResult
    ) -> ProductExtraction:
        source = KGSource(
            dataset_id="image-evaluation",
            dataset_version_id="image-evaluation-v1",
            file=document.asset_ref,
            text=document.text,
            content_revision=document.content_revision,
            extractor=self.identity,
            block_start=block.start,
            block_end=block.end,
        )
        product = assemble_extraction(result.output, self.schema, source)
        return enrich_image_product(product, document, self.schema, raw=result.output)

    def _extract(
        self, case: KGImageCase, document: KGDocument, transcript: TranscriptionResult
    ) -> ImageCaseExecution:
        products: list[ProductExtraction] = []
        failures: list[KGEvalFailure] = []
        entities: list[ScoredEntity] = []
        relations: list[ScoredRelation] = []
        for block in document.blocks:
            try:
                result = checked_extract(self.extractor, block, self.schema)
            except KGExtractionError as error:
                failures.append(
                    KGEvalFailure(
                        case_id=case.id, start=block.start, end=block.end, reason=error.reason
                    )
                )
                continue
            entities.extend(
                ScoredEntity(name=item.name, type=item.type) for item in result.output.entities
            )
            relations.extend(raw_relations(result.output, document.text))
            products.append(self._product(document, block, result))
        product = ProductExtraction(
            entities=tuple(
                {
                    entity.asset_ref.asset_id: entity
                    for item in products
                    for entity in item.entities
                }.values()
            ),
            drafts=tuple(draft for item in products for draft in item.drafts),
            proposals=tuple(proposal for item in products for proposal in item.proposals),
        )
        persisted = store_evaluation_product(self.db, product, self.schema)
        predictions, candidates = image_predictions(persisted, product, document.text)
        raw = ScoredRecord(
            pid=case.id,
            entities=tuple(entities),
            relations=tuple(relations),
            error=";".join(item.reason for item in failures) or None,
            failed_blocks=len(failures),
        )
        return ImageCaseExecution(
            raw=raw,
            product=raw.model_copy(update={"entities": predictions, "relations": candidates}),
            blocked=blocked_relations(case.id, tuple(products)),
            failures=tuple(failures),
            transcript=transcript,
        )

    def _failed(self, case: KGImageCase, error: TranscriptionFailure) -> ImageCaseExecution:
        record = ScoredRecord(pid=case.id, error=f"transcription:{error.reason}", failed_blocks=1)
        return ImageCaseExecution(
            raw=record,
            product=record,
            blocked=(),
            failures=(
                KGEvalFailure(
                    case_id=case.id,
                    start=0,
                    end=0,
                    reason=record.error or "transcription_failed",
                    message="服务商额度不足"
                    if "provider_quota_exhausted" in error.result.quality_issues
                    else None,
                ),
            ),
            transcript=error.result,
        )

    def execute(self, case: KGImageCase, path: Path) -> ImageCaseExecution:
        """Keep transcription failure visible and never extract from rejected output."""
        try:
            image = normalize_image(path.read_bytes())
            if (case.width and case.width != image.width) or (
                case.height and case.height != image.height
            ):
                msg = "Image case dimensions differ from orientation-corrected pixels"
                raise ValidationError(msg)
            transcript = checked_transcribe(self.transcriber, image, self.transcription.mode)
        except TranscriptionUnavailableError as error:
            result = TranscriptionResult(
                text="",
                width=case.width or 1,
                height=case.height or 1,
                backend=self.transcription.backend,
                model=self.transcription.model,
                mode=self.transcription.mode,
                error=str(error),
                quality_issues=(error.reason,),
            )
            return self._failed(case, TranscriptionFailure(error.reason, result))
        except TranscriptionFailure as error:
            return self._failed(case, error)
        if (transcript.width, transcript.height) != (image.width, image.height):
            msg = "Transcription geometry differs from orientation-corrected pixels"
            raise ValidationError(msg)
        return self._extract(case, self._document(case, image, transcript), transcript)
