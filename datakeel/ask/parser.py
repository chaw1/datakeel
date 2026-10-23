# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose deterministic lexical and temporal parsing without database access."""

from datakeel.ask.matching import metric_matches
from datakeel.ask.time import parse_time
from datakeel.core.ask_models import AskRequest, ParsedQuestion
from datakeel.core.metric_models import SemanticLayer


def parse_question(request: AskRequest, layer: SemanticLayer) -> ParsedQuestion:
    """Return NFC text anchors and date bounds for registered candidate metrics."""
    temporal = parse_time(request.question, request.reference_instant)
    return ParsedQuestion(
        question=request.question,
        matches=metric_matches(request.question, layer) + temporal.matches,
        time_range=temporal.time_range,
        issues=temporal.issues,
    )
