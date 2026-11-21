# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded bilingual tool discovery without storage or execution dependencies."""

from __future__ import annotations

import math
import re
from collections import Counter
from functools import lru_cache
from typing import TYPE_CHECKING

from pydantic import Field

from datakeel.core.agent_models import ToolDefinition
from datakeel.core.json_schema import compact_schema
from datakeel.core.models import BoundaryModel, JsonDocument
from datakeel.ontology.functions import function_definitions

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

DEFAULT_TOOL_SEARCH_LIMIT = 8
_NAME_WEIGHT = 3
_BM25_K1 = 1.2
_BM25_B = 0.75
_MIN_PLURAL_LENGTH = 4
_WORDS = re.compile(r"[a-z0-9]+|[\u3400-\u9fff]+")


class _ResidentToolSearchParams(BoundaryModel):
    query: str = Field(min_length=1, max_length=200)


class ToolSearchParams(BoundaryModel):
    """Search read tool names or controlled action names and effects."""

    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=DEFAULT_TOOL_SEARCH_LIMIT, ge=1, le=20)


def tool_search_definition() -> ToolDefinition:
    """Advertise bounded discovery while preserving the exact resident tool schema size."""
    return ToolDefinition(
        name="tool_search",
        description="Discover reads and prepare-only actions.",
        parameters=compact_schema(
            JsonDocument.model_validate(_ResidentToolSearchParams.model_json_schema())
        ),
    )


def _tokens(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORDS.findall(text.casefold()):
        if not word.isascii():
            tokens.extend(word)
            tokens.extend(word[index : index + 2] for index in range(len(word) - 1))
        elif (
            len(word) >= _MIN_PLURAL_LENGTH
            and word.endswith("s")
            and not word.endswith(("ss", "us", "is"))
        ):
            tokens.append(word[:-1])
        else:
            tokens.append(word)
    return tokens


def _score(
    document: Counter[str], query: set[str], frequencies: Counter[str], average: float, count: int
) -> float:
    normalization = _BM25_K1 * (1 - _BM25_B + _BM25_B * document.total() / average)
    return sum(
        math.log1p((count - frequencies[token] + 0.5) / (frequencies[token] + 0.5))
        * document[token]
        * (_BM25_K1 + 1)
        / (document[token] + normalization)
        for token in sorted(query.intersection(document))
    )


def _rank(
    tools: Sequence[ToolDefinition], query: str, extra_text: Mapping[str, str]
) -> list[ToolDefinition]:
    tokens = set(_tokens(query))
    if not tokens:
        return sorted(
            (
                tool
                for tool in tools
                if query
                and query
                in f"{tool.name} {tool.description} {extra_text.get(tool.name, '')}".casefold()
            ),
            key=lambda tool: tool.name,
        )
    documents = [
        Counter(
            _tokens(tool.name) * _NAME_WEIGHT
            + _tokens(f"{tool.description} {extra_text.get(tool.name, '')}")
        )
        for tool in tools
    ]
    frequencies = Counter(token for document in documents for token in document)
    average = sum(document.total() for document in documents) / max(len(documents), 1) or 1
    scored = [
        (_score(document, tokens, frequencies, average, len(documents)), tool)
        for tool, document in zip(tools, documents, strict=True)
    ]
    return [
        tool
        for score, tool in sorted(scored, key=lambda item: (-item[0], item[1].name))
        if score > 0
    ]


@lru_cache(maxsize=1)
def _read_search_texts() -> dict[str, str]:
    return {
        item.id: " ".join(
            text for texts in (*item.phrases.values(), *item.examples.values()) for text in texts
        )
        for item in function_definitions()
    }


def search_tools(
    tools: Sequence[ToolDefinition],
    params: ToolSearchParams,
    *,
    extra_text: Mapping[str, str] | None = None,
) -> JsonDocument:
    """Return exact names first, otherwise BM25 matches with a deterministic schema cap."""
    query = params.query.strip().casefold()
    name = re.sub(r"[\s-]+", "_", query)
    exact = next((tool for tool in tools if tool.name.casefold() == name), None)
    text_index = _read_search_texts() if extra_text is None else extra_text
    matches = [exact] if exact is not None else _rank(tools, query, text_index)
    return JsonDocument.model_validate(
        {
            "tools": [tool.model_dump(mode="json") for tool in matches[: params.limit]],
            "total_matches": len(matches),
            "truncated": len(matches) > params.limit,
        }
    )
