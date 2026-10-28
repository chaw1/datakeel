# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""ASCII and Unicode punctuation variants share one documented text similarity signal."""

import string

from datakeel.training.hashes import normalize_text, simhash


def test_simhash_ignores_all_ascii_punctuation_and_compatibility_variants() -> None:
    """Currency and mathematical ASCII punctuation are included alongside Unicode P marks."""
    original = "Generated observation harbor ferry"
    variant = f"GENERATED{string.punctuation}observation\tHarbor{chr(0xFF0C)}FERRY{chr(0xFF01)}"
    assert normalize_text(variant) == normalize_text(original)
    assert simhash(variant) == simhash(original)
    fullwidth = "".join(
        chr(ord(character) + 0xFEE0) if character != " " else character
        for character in "GENERATED+observation$Harbor Ferry"
    )
    assert simhash(fullwidth) == simhash(original)
