# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Share whole catalog identifiers and stop words across linking and subject resolution."""

import re
import unicodedata

_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*")
_STOP_WORDS = frozenset({"table", "tables", "the", "表"})


def catalog_identifiers(text: str) -> tuple[str, ...]:
    """Extract whole ASCII identifiers, retaining underscores and qualified segments."""
    return tuple(
        dict.fromkeys(
            match.group().lower()
            for match in _IDENTIFIER.finditer(text)
            if match.group().lower() not in _STOP_WORDS
        )
    )


def normalized_subject_name(text: str) -> str:
    """Normalize a complete subject while discarding only standalone catalog stop words."""
    text = unicodedata.normalize("NFKC", text).strip().lower()
    text = _IDENTIFIER.sub(
        lambda match: "" if match.group() in _STOP_WORDS else match.group(), text
    )
    return " ".join(part for part in text.split() if part not in _STOP_WORDS)
