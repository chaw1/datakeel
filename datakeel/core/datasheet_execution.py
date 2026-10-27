# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen inputs and fenced completion for optional datasheet model jobs."""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime

from datakeel.core.agent_models import ConversationCreate
from datakeel.core.datasheet_models import DatasheetDocument, DatasheetFact, DatasheetLanguage
from datakeel.core.harness_pricing import ModelPrice
from datakeel.core.models import BoundaryModel


class DatasheetPrepared(BoundaryModel):
    """Bind the exact outgoing facts and provider limits to the reviewed plan."""

    facts: tuple[DatasheetFact, ...]
    config: ConversationCreate
    target_url: str | None = None
    input_tokens: int = 0
    estimated_cost_usd: Decimal = Decimal(0)
    price: ModelPrice | None = None
    price_version: str | None = None
    external: bool = False


class DatasheetJob(BoundaryModel):
    """Expose durable task progress without leaking the frozen outgoing fact payload."""

    id: str
    task_id: str
    dataset_id: str
    version_id: str
    language: DatasheetLanguage
    created_at: AwareDatetime
    provider: Literal["fake", "openai", "anthropic"] = "fake"
    status: Literal["QUEUED", "COMPLETED", "FAILED", "CANCELLED"] = "QUEUED"
    document_id: str | None = None
    error: str | None = None


class DatasheetCompletion(BoundaryModel):
    """Publish a checked model document only inside the owned queue completion."""

    job_id: str
    document: DatasheetDocument


class DatasheetFence(BoundaryModel):
    """Bind optional model invocation to the currently owned queue shard."""

    task_id: str
    shard_id: str
    owner: str
