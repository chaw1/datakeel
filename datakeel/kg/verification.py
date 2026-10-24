# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find model quotations while preserving source Unicode code-point intervals."""

import unicodedata

from datakeel.core.evidence_models import TextSpan


def _occurrences(text: str, quote: str) -> tuple[TextSpan, ...]:
    result: list[TextSpan] = []
    position = text.find(quote)
    while position >= 0:
        result.append(TextSpan(start=position, end=position + len(quote)))
        position = text.find(quote, position + 1)
    return tuple(result)


def _normalized(text: str) -> tuple[str, list[tuple[int, int]]]:
    normalized: list[str] = []
    offsets: list[tuple[int, int]] = []
    clusters: list[tuple[int, int]] = []
    for index, character in enumerate(text):
        if clusters and unicodedata.combining(character):
            clusters[-1] = (clusters[-1][0], index + 1)
        else:
            clusters.append((index, index + 1))
    for start, end in clusters:
        for token in unicodedata.normalize("NFKC", text[start:end]).casefold():
            if not token.isspace():
                normalized.append(token)
                offsets.append((start, end))
    return "".join(normalized), offsets


def find_spans(text: str, quote: str) -> tuple[TextSpan, ...]:
    """Prefer exact quotation matches, otherwise map NFKC/case/space matches to source."""
    if not quote:
        return ()
    exact = _occurrences(text, quote)
    if exact:
        return exact
    return _normalized_spans(text, quote)


def _normalized_spans(text: str, quote: str) -> tuple[TextSpan, ...]:
    source, offsets = _normalized(text)
    needle = "".join(unicodedata.normalize("NFKC", quote).casefold().split())
    if not needle:
        return ()
    return tuple(
        TextSpan(start=offsets[span.start][0], end=offsets[span.end - 1][1])
        for span in _occurrences(source, needle)
    )


def nearest_span(spans: tuple[TextSpan, ...], evidence: TextSpan | None) -> TextSpan | None:
    """Choose the occurrence nearest the quotation, breaking equal distances forward."""
    if not spans:
        return None
    if evidence is None:
        return min(spans, key=lambda span: span.start)
    return min(
        spans,
        key=lambda span: (max(evidence.start - span.end, span.start - evidence.end, 0), span.start),
    )


def entity_spans(text: str, names: tuple[str, ...]) -> tuple[TextSpan, ...]:
    """Collect every supported spelling occurrence in stable document order."""
    spans = {
        (span.start, span.end): span
        for name in names
        for span in (*find_spans(text, name), *_normalized_spans(text, name))
    }
    return tuple(spans[key] for key in sorted(spans))
