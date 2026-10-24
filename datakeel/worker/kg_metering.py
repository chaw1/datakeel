# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Meter each actual adapter invocation with the existing durable budget and trace store."""

from time import perf_counter

from pydantic import ValidationError as ModelValidationError

from datakeel.core.context_tokens import estimate_tokens
from datakeel.core.errors import BudgetError, ProviderError
from datakeel.core.harness_models import (
    BudgetLimits,
    BudgetRequest,
    TokenSegment,
    TokenUsage,
    TraceInput,
)
from datakeel.core.kg_contracts import KGSchema
from datakeel.core.kg_errors import ExtractionProviderError, KGExtractionError
from datakeel.core.kg_execution import KGMeteringConfig
from datakeel.core.kg_models import ExtractionResult, TextBlock
from datakeel.kg.extractors import ExtractorAdapter
from datakeel.kg.prompt import extraction_prompt
from datakeel.storage.budget_service import reserve
from datakeel.storage.database import Database
from datakeel.storage.harness_service import list_traces, settle


def _failure(error: Exception) -> str:
    if isinstance(error, ProviderError | KGExtractionError):
        return error.reason
    if isinstance(error, ModelValidationError | ValueError | TypeError):
        return "parse_failure"
    return "timeout" if isinstance(error, TimeoutError) else "extractor_error"


class MeteredExtractor:
    """Keep provider observations separate from conservative unknown-price charges."""

    def __init__(self, db: Database, config: KGMeteringConfig, adapter: ExtractorAdapter) -> None:
        """Bind one adapter to a durable extraction identity and frozen tariff snapshot."""
        self.db, self.config, self.adapter = db, config, adapter
        existing = list_traces(db, config.run_id)
        self.turn = max((trace.turn for trace in existing), default=0)
        self.exceeded = any(trace.budget_exceeded for trace in existing)

    def _reserve(self, block: TextBlock, schema: KGSchema) -> str:
        if self.exceeded:
            msg = "Extraction budget exceeded after observed provider usage"
            raise BudgetError(msg)
        config = self.config
        reservation = reserve(
            self.db,
            BudgetRequest(
                conversation_id=config.run_id,
                model=config.profile.model,
                input_tokens=estimate_tokens(extraction_prompt(block, schema)),
                max_output_tokens=config.profile.max_output_tokens,
                limits=BudgetLimits(
                    conversation_tokens=config.budget_tokens, conversation_usd=config.max_cost_usd
                ),
            ),
            config.price_version,
            config.price,
        )
        return reservation.id

    def _settle(
        self, reservation_id: str, started: float, observed: TokenUsage | None, reason: str
    ) -> None:
        config = self.config
        offline = config.profile.extractor != "llm"
        unknown = not offline and (not config.known_price or observed is None)
        usage = observed if observed is not None and not unknown and not offline else TokenUsage()
        self.turn += 1
        trace = settle(
            self.db,
            reservation_id,
            TraceInput(
                conversation_id=config.run_id,
                turn=self.turn,
                model=config.profile.model,
                provider=config.profile.provider,
                segments=[TokenSegment(name="extraction", tokens=usage.input_tokens)],
                usage=usage,
                observed_usage=observed if unknown else None,
                latency_ms=(perf_counter() - started) * 1000,
                stop_reason=reason,
                tool_calls=0,
                billing_status="unknown" if unknown else "actual",
                call_type="extraction",
            ),
        )
        self.exceeded = self.exceeded or trace.budget_exceeded

    def extract(self, block: TextBlock, schema: KGSchema) -> ExtractionResult:
        """Reserve before one request, then settle failures and truncation before returning."""
        reservation = self._reserve(block, schema)
        started = perf_counter()
        try:
            result = self.adapter.extract(block, schema)
        except Exception as error:
            reason = _failure(error)
            observed = (
                error.observed_usage
                if isinstance(error, KGExtractionError | ExtractionProviderError)
                else None
            )
            self._settle(reservation, started, observed, reason)
            raise KGExtractionError(reason, observed_usage=observed) from error
        observed = (
            TokenUsage(
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_read_tokens=result.cache_read_tokens,
                cache_write_tokens=result.cache_write_tokens,
            )
            if result.input_tokens is not None and result.output_tokens is not None
            else None
        )
        self._settle(reservation, started, observed, result.finish_reason)
        return result
