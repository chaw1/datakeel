# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Derive concise measurement names while retaining their object and qualifying modifiers."""

import re
from functools import lru_cache

from datakeel.datasheets.vocabulary import (
    COUNT_LABEL_SUFFIXES,
    FIELD_LABELS,
    MEASUREMENT_SCOPES,
    SCORE_LABEL_SUFFIXES,
    field_label,
)

_Vocabulary = tuple[tuple[str, tuple[str, str]], ...]
_HAN = re.compile(r"[\u3400-\u9fff]")


def _plural(word: str) -> str:
    if word.endswith("y") and len(word) > 1 and word[-2] not in "aeiou":
        return word[:-1] + "ies"
    return word if word.endswith("s") else word + "s"


def _english(label: str) -> tuple[str, ...]:
    words = tuple(label.casefold().split())
    if not words or words[-1] not in {"count", "counts", "score"}:
        return ()
    scopes = {english for _chinese, english in MEASUREMENT_SCOPES}
    stems = (words[:-1], tuple(word for word in words[:-1] if word not in scopes))
    labels: list[str] = []
    for stem in stems:
        if not stem:
            continue
        base = " ".join(stem)
        if words[-1] == "score":
            labels.extend(f"{base} {suffix}" for suffix in ("score", "total", "rating"))
        else:
            plural = " ".join((*stem[:-1], _plural(stem[-1])))
            labels.extend(
                (f"{base} count", f"{base} total", plural, f"total {plural}", f"number of {plural}")
            )
    return tuple(labels)


def _chinese_scopes(stem: str) -> tuple[str, ...]:
    forms = {stem}
    for chinese, _english in MEASUREMENT_SCOPES:
        forms.update(text.replace(chinese, "") for text in tuple(forms))
    return tuple(sorted(form for form in forms if form))


def _strip_suffix(label: str, suffixes: tuple[str, ...]) -> str | None:
    return next((label[: -len(suffix)] for suffix in suffixes if label.endswith(suffix)), None)


def _connectors(stem: str, original: str, vocabulary: _Vocabulary) -> tuple[str, ...]:
    forms = {stem}
    for _field, (chinese, english) in vocabulary:
        if chinese == original or english.casefold().split()[-1:] not in (["count"], ["counts"]):
            continue
        shorter = _strip_suffix(chinese, COUNT_LABEL_SUFFIXES)
        if shorter is not None:
            for suffix in _chinese_scopes(shorter):
                if stem != suffix and stem.endswith(suffix):
                    forms.add(stem[: -len(suffix)] + "的" + suffix)
    return tuple(sorted(forms))


def _chinese(chinese: str, english: str, vocabulary: _Vocabulary) -> tuple[str, ...]:
    if english.casefold().split()[-1:] == ["score"]:
        stem = _strip_suffix(chinese, SCORE_LABEL_SUFFIXES)
        return () if stem is None else tuple(stem + suffix for suffix in SCORE_LABEL_SUFFIXES)
    if english.casefold().split()[-1:] not in (["count"], ["counts"]):
        return ()
    stem = _strip_suffix(chinese, COUNT_LABEL_SUFFIXES)
    if stem is None:
        return ()
    return tuple(
        form + suffix
        for variant in _chinese_scopes(stem)
        for form in _connectors(variant, chinese, vocabulary)
        for suffix in (*COUNT_LABEL_SUFFIXES, "")
    )


def short_measurement_labels(field: str) -> tuple[str, ...]:
    """Generate count and score short forms from the field's bilingual display names."""
    chinese, english = field_label(field, "zh"), field_label(field, "en")
    return tuple(
        dict.fromkeys(
            (*_english(english), *_chinese(chinese, english, tuple(FIELD_LABELS.items())))
        )
    )


@lru_cache(maxsize=16)
def _known_labels(vocabulary: _Vocabulary) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            label.casefold()
            for _field, (chinese, english) in vocabulary
            for label in (
                chinese,
                english,
                *_english(english),
                *_chinese(chinese, english, vocabulary),
            )
        )
    )


@lru_cache(maxsize=1024)
def _pattern(label: str) -> re.Pattern[str]:
    pattern = re.escape(label)
    return re.compile(pattern if _HAN.search(label) else r"(?<!\w)" + pattern + r"(?!\w)")


def unshadowed_label(context: str, label: str) -> bool:
    """Require one complete label occurrence outside any longer registered measurement name."""
    longer = tuple(
        other
        for other in _known_labels(tuple(FIELD_LABELS.items()))
        if len(other) > len(label) and label in other
    )
    return any(
        not any(
            enclosing.start() <= match.start() and match.end() <= enclosing.end()
            for other in longer
            for enclosing in _pattern(other).finditer(context)
        )
        for match in _pattern(label).finditer(context)
    )
