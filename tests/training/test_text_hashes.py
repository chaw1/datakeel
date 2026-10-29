# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent normalization invariants and fixed stable simhash fingerprints."""

import hashlib

from datakeel.training.text_hashes import normalize_text, simhash


def test_formatting_variants_have_identical_normalized_text_and_hash() -> None:
    """Whitespace, Unicode or ASCII punctuation and case retain distance zero."""
    variants = (
        "A brief description, of a brown fox!",
        " a BRIEF description of a brown FOX ",
        "A\r\nbrief\tdescription of\u2003a brown\rFOX",
        "a!b?r;i:e,f d/e+s=c<r>i^p~t`i|o_n[o]f{a}b\\r\"o'w:n.f,o;x",
        "\uff21 brief description\uff0cof a brown fox\uff01",
        "\U0001d400 brief description of a brown fox",
        "a brief description—of a brown fox…",
    )
    original = "A brief description of a brown fox"
    for variant in variants:
        assert normalize_text(variant) == "abriefdescriptionofabrownfox"
        assert simhash(variant) == simhash(original)


def test_unicode_canonical_composition_and_casefold_are_stable() -> None:
    """Composed/decomposed accents and case expansions keep their Unicode content identity."""
    assert normalize_text("CAFÉ Straße\r\n中文。") == "caféstrasse中文"
    assert simhash("CAFÉ Straße\r\n中文。") == simhash("cafe\u0301 STRASSE\t中 文")
    assert simhash("🦊") != simhash("🦉")


def test_removing_formatting_recomposes_combining_characters_idempotently() -> None:
    """Punctuation or whitespace inserted inside a combining sequence cannot alter its hash."""
    for original, variants in (
        ("cafe\u0301", ("cafe!\u0301", "cafe \u0301", "CAFÉ")),
        ("Å", ("A \u030a", "A—\u030a", "a\u030a")),
    ):
        normalized = normalize_text(original)
        assert normalize_text(normalized) == normalized
        for variant in variants:
            assert normalize_text(variant) == normalized
            assert simhash(variant) == simhash(original)


def test_empty_punctuation_has_no_similarity_signal_and_short_text_uses_one_feature() -> None:
    """Empty canonical content cannot create a universal false-positive similarity bucket."""
    for empty in ("", " \r\n\t", "!?—。", "[+]<=>"):
        assert simhash(empty) is None
    assert simhash("AB") == int.from_bytes(hashlib.sha256(b"ab").digest()[:8], "big")
    assert simhash("Z") == int.from_bytes(hashlib.sha256(b"z").digest()[:8], "big")


def test_simhash_stable_fingerprint_keeps_feature_multiplicities_and_zero_ties() -> None:
    """A fixed public synthetic phrase locks deterministic weighting, digest bytes and tie bits."""
    assert simhash("ababa abaca") == 0x6024ACC0F5F32E88


def test_zero_width_formatting_cannot_hide_an_identical_text() -> None:
    """All five specified invisible formats vanish before hashing and Unicode recomposition."""
    for invisible in "\u200b\u200c\u200d\u2060\ufeff":
        for text in ("A brown fox", "订单已经发货", "cafe\u0301"):
            variant = invisible.join(text)
            assert normalize_text(variant) == normalize_text(text)
            assert simhash(variant) == simhash(text)
        assert normalize_text(invisible) == ""
        assert simhash(invisible) is None
