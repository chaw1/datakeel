# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Reserve and settle image transcription independently from downstream extraction."""

from collections.abc import Callable
from time import perf_counter

from datakeel.core.errors import BudgetError, ConflictError
from datakeel.core.harness_models import (
    BudgetLimits,
    BudgetRequest,
    TokenSegment,
    TokenUsage,
    TraceInput,
)
from datakeel.core.kg_execution import KGJob
from datakeel.core.transcription_errors import TranscriptionFailure
from datakeel.core.transcription_models import ImageInput, TranscriptionMode, TranscriptionResult
from datakeel.storage.budget_service import reserve
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces, settle
from datakeel.transcription.auto_adapter import AutoTranscriber
from datakeel.transcription.factory import prepare_transcriber
from datakeel.transcription.prompt import input_token_bound
from datakeel.transcription.quality import TranscriberAdapter


class MeteredTranscriber:
    """Record only actual visual model attempts and preserve conservative unknown charges."""

    def __init__(
        self,
        db: Database,
        job: KGJob,
        adapter: TranscriberAdapter,
        before_request: Callable[[], bool] | None = None,
    ) -> None:
        """Bind the already authorized profile and its frozen tariff to this run."""
        self.db, self.job, self.adapter = db, job, adapter
        self.before_request = before_request
        self.exceeded = any(trace.budget_exceeded for trace in list_traces(db, job.run.id))

    def _settle(self, reservation: str, started: float, result: TranscriptionResult) -> None:
        prepared = self.job.prepared
        profile, estimate = prepared.transcription_profile, prepared.transcription_estimate
        if profile is None or estimate is None:
            msg = "Transcription metering requires a frozen profile and estimate"
            raise ValueError(msg)
        observed = (
            TokenUsage(input_tokens=result.input_tokens, output_tokens=result.output_tokens)
            if result.input_tokens is not None and result.output_tokens is not None
            else None
        )
        unknown = estimate.price is None or observed is None
        traces = list_traces(self.db, self.job.run.id)
        trace = settle(
            self.db,
            reservation,
            TraceInput(
                conversation_id=self.job.run.id,
                turn=max((trace.turn for trace in traces), default=0) + 1,
                model=profile.model,
                provider=profile.interface,
                segments=[
                    TokenSegment(
                        name="transcription",
                        tokens=observed.input_tokens if observed and not unknown else 0,
                    )
                ],
                usage=observed if observed is not None and not unknown else TokenUsage(),
                observed_usage=observed if unknown else None,
                latency_ms=(perf_counter() - started) * 1000,
                stop_reason=result.error or result.finish_reason,
                tool_calls=0,
                billing_status="unknown" if unknown else "actual",
                call_type="transcription",
            ),
        )
        self.exceeded = self.exceeded or trace.budget_exceeded

    def transcribe(
        self, image: ImageInput, mode: TranscriptionMode | None = None
    ) -> TranscriptionResult:
        """Budget visual requests; replay, scripted output and OCR have no remote model charge."""
        prepared = self.job.prepared
        profile, price = prepared.transcription_profile, prepared.transcription_accounting_price
        if profile is None or price is None:
            msg = "Transcription metering requires prepared inputs"
            raise ValueError(msg)
        selected = mode or profile.mode
        if selected == "auto" and isinstance(self.adapter, AutoTranscriber):
            selected = self.adapter.resolve(image).route
        if profile.backend != "vlm" or selected == "ocr":
            return self.adapter.transcribe(image, mode)
        if self.exceeded:
            msg = "Transcription budget exceeded after observed provider usage"
            raise BudgetError(msg)
        prepare_transcriber(self.adapter, image, mode)
        if self.before_request is not None and not self.before_request():
            msg = "Graph worker lease was lost before a visual model request"
            raise ConflictError(msg)
        reservation = reserve(
            self.db,
            BudgetRequest(
                conversation_id=self.job.run.id,
                model=profile.model,
                input_tokens=input_token_bound(
                    image.width, image.height, profile.prompt_version, profile.coordinate_space
                ),
                max_output_tokens=profile.max_output_tokens,
                limits=BudgetLimits(
                    conversation_tokens=self.job.budget_tokens,
                    conversation_usd=self.job.max_cost_usd,
                ),
            ),
            prepared.transcription_accounting_version or "unknown",
            price,
        )
        started = perf_counter()
        try:
            result = self.adapter.transcribe(image, mode)
        except Exception as error:
            result = (
                error.result
                if isinstance(error, TranscriptionFailure)
                else TranscriptionResult(
                    text="",
                    width=image.width,
                    height=image.height,
                    backend=profile.backend,
                    model=profile.model,
                    mode=mode or profile.mode,
                    error="timeout" if isinstance(error, TimeoutError) else "provider_error",
                )
            )
            self._settle(reservation.id, started, result)
            raise
        self._settle(reservation.id, started, result)
        return result
