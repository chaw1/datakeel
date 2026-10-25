# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ground evidence fragments in OCR lines using exact and bounded fuzzy matching."""

import re
import unicodedata

from datakeel.core.evidence_models import ImageRegion
from datakeel.core.transcription_models import OCRLine

_SPLIT = re.compile(r"-{1,3}>|<-{1,3}|→|←|\||\n|\s--\s|--|\.\.\.|…")
_DROP = re.compile(r"[\s`*#>~\\]")
_PUNCTUATION = re.compile(r"[:\uff1a\uff08\uff09()\[\],\uff0c。.]+")
_MIN_PIECE = 2
_MIN_FUZZY = 3
_FUZZY_THRESHOLD = 0.8
type _Occurrence = frozenset[int]


def normalize(text: str) -> str:
    """Apply the recording scorer's NFKC, lowercase and markdown normalization."""
    return _DROP.sub("", unicodedata.normalize("NFKC", text).lower())


def _lcs_length(needle: str, haystack: str) -> int:
    masks: dict[str, int] = {}
    for index, char in enumerate(needle):
        masks[char] = masks.get(char, 0) | (1 << index)
    state = 0
    for char in haystack:
        matches = masks.get(char, 0) | state
        state = matches & ~(matches - ((state << 1) | 1))
    return state.bit_count()


def _partial_alignment(piece: str, hay: str) -> tuple[int, int] | None:
    """Compute partial normalized Indel similarity without an optional fuzzy dependency."""
    if not piece or not hay:
        return None
    if len(piece) > len(hay):
        return (0, len(hay)) if _partial_alignment(hay, piece) is not None else None
    length = len(piece)
    best = _FUZZY_THRESHOLD
    selected: tuple[int, int] | None = None
    windows = [(0, end) for end in range(1, min(length, len(hay)))]
    windows.extend((start, min(start + length, len(hay))) for start in range(len(hay)))
    for start, end in windows:
        segment = hay[start:end]
        score = 2 * _lcs_length(piece, segment) / (length + len(segment))
        if score >= best and (selected is None or score > best):
            best, selected = score, (start, end)
    return selected


def _occurrences(
    piece: str, hay: str, owners: list[int], *, fuzzy: bool = True
) -> list[_Occurrence]:
    occurrences: list[_Occurrence] = []
    start = 0
    while (index := hay.find(piece, start)) >= 0:
        occurrences.append(frozenset(owners[index : index + len(piece)]))
        start = index + 1
    if not occurrences and fuzzy and len(piece) >= _MIN_FUZZY:
        alignment = _partial_alignment(piece, hay)
        if alignment is not None:
            occurrences.append(frozenset(owners[alignment[0] : alignment[1]]))
    return occurrences


def _fragments(evidence: str, hay: str, owners: list[int]) -> list[list[_Occurrence]]:
    found: list[list[_Occurrence]] = []
    for raw in _SPLIT.split(evidence):
        piece = normalize(raw)
        if len(piece) < _MIN_PIECE or _PUNCTUATION.fullmatch(piece):
            continue
        multi = len(raw.split()) > 1
        occurrences = _occurrences(piece, hay, owners, fuzzy=not multi)
        if not occurrences and multi:
            words = [normalize(word) for word in raw.split() if len(normalize(word)) >= _MIN_PIECE]
            groups = [_occurrences(word, hay, owners, fuzzy=False) for word in words]
            if words and all(groups):
                found.extend(groups)
                continue
            occurrences = _occurrences(piece, hay, owners)
        if occurrences:
            found.append(occurrences)
    return found


def _box(lines: tuple[OCRLine, ...], indices: _Occurrence) -> tuple[float, float, float, float]:
    boxes = [lines[index].bbox for index in indices]
    return (
        min(box[0] for box in boxes),
        min(box[1] for box in boxes),
        max(box[2] for box in boxes),
        max(box[3] for box in boxes),
    )


def _center(lines: tuple[OCRLine, ...], indices: _Occurrence) -> tuple[float, float]:
    x1, y1, x2, y2 = _box(lines, indices)
    return (x1 + x2) / 2, (y1 + y2) / 2


def align_regions(
    evidence: str, lines: tuple[OCRLine, ...], width: int, height: int
) -> tuple[ImageRegion, ...]:
    """Keep one rectangle per matched fragment, anchoring repetitions to the rarest fragment."""
    normalized = [normalize(line.text) for line in lines]
    owners = [index for index, text in enumerate(normalized) for _ in text]
    found = _fragments(evidence, "".join(normalized), owners)
    if not found:
        return ()
    found.sort(key=len)
    selected = [found[0][0]]
    anchor_x, anchor_y = _center(lines, selected[0])
    selected.extend(
        min(
            occurrences,
            key=lambda indices: (
                (_center(lines, indices)[0] - anchor_x) ** 2
                + (_center(lines, indices)[1] - anchor_y) ** 2
            ),
        )
        for occurrences in found[1:]
    )
    boxes = dict.fromkeys(_box(lines, indices) for indices in selected)
    return tuple(ImageRegion(bbox=box, width=width, height=height) for box in boxes)


def match_box(
    evidence: str, lines: tuple[OCRLine, ...], width: int, height: int
) -> tuple[float, float, float, float] | None:
    """Merge fragment boxes for the original recording-score coordinate convention."""
    regions = align_regions(evidence, lines, width, height)
    if not regions:
        return None
    return (
        min(region.bbox[0] for region in regions),
        min(region.bbox[1] for region in regions),
        max(region.bbox[2] for region in regions),
        max(region.bbox[3] for region in regions),
    )
