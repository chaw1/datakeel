# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unregistered word forms and abbreviations exercise vocabulary-free lexical rules."""

import pytest
from pydantic import ValidationError

from datakeel.standards.lexical import TokenMatch, match_token


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("reconc", "reconciliation"),
        ("fulf", "fulfillment"),
        ("consig", "consignment"),
        ("reserv", "reservation"),
        ("receiv", "receivable"),
        ("procur", "procurement"),
    ],
)
def test_unregistered_prefix_returns_discounted_match(observed: str, expected: str) -> None:
    """Partial leading words generalize without adding aliases to a vocabulary."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "prefix"
    assert 0.65 <= result.weight <= 0.9


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("invoiced", "invoice"),
        ("shipping", "ship"),
        ("shipped", "shipping"),
        ("payment", "pay"),
        ("paid", "payment"),
        ("approved", "approval"),
        ("delivered", "deliver"),
        ("allocation", "allocate"),
        ("computation", "compute"),
        ("shipments", "ship"),
        ("batches", "batch"),
        ("categories", "category"),
    ],
)
def test_inflection_and_derivation_share_word_root(observed: str, expected: str) -> None:
    """Regular suffixes, doubled consonants and an irregular payment root normalize."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "morphology"
    assert result.weight == 0.94


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("colour", "color"),
        ("flavours", "flavor"),
        ("behaviour", "behavior"),
        ("authorise", "authorize"),
        ("organisation", "organization"),
        ("catalogue", "catalog"),
        ("centred", "center"),
        ("metre", "meter"),
    ],
)
def test_systematic_spelling_variants_normalize(observed: str, expected: str) -> None:
    """Regional spelling transforms also compose with regular inflection rules."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "spelling"
    assert result.weight == 0.94


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("dscnt", "discount"),
        ("spplr", "supplier"),
        ("prchs", "purchase"),
        ("shpmnt", "shipment"),
        ("rcpt", "receipt"),
        ("wrnty", "warranty"),
        ("invc", "invoice"),
        ("nvc", "invoice"),
        ("tkt", "ticket"),
        ("qty", "quantity"),
        ("amt", "amount"),
        ("dt", "date"),
    ],
)
def test_consonant_skeletons_support_bounded_omission(observed: str, expected: str) -> None:
    """Vowels and limited consonants may be omitted without per-word abbreviation lists."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "consonant"
    assert 0.7 <= result.weight <= 0.85


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("", "invoice"),
        ("ship", ""),
        ("re", "revenue"),
        ("ticket", "tkt"),
        ("table", "ticket"),
        ("st", "shipment"),
        ("ttc", "ticket"),
        ("kstmr", "customer"),
        ("ct", "customer"),
        ("million", "mill"),
        ("x123", "x"),
        ("客户", "customer"),
    ],
)
def test_unrelated_or_insufficient_tokens_abstain(observed: str, expected: str) -> None:
    """Lexical matching rejects arbitrary edits and excessively short subsequences."""
    assert match_token(observed, expected) is None


def test_exact_matches_preserve_evidence_and_outrank_variations() -> None:
    """Case-insensitive identity preserves the original evidence and maximum weight."""
    result = match_token("Customer", "customer")
    assert result == TokenMatch(weight=1.0, rule="exact", observed="Customer", expected="customer")


def test_prefix_confidence_increases_with_retained_word_length() -> None:
    """A longer retained prefix supplies more lexical evidence than a short one."""
    short = match_token("rec", "reconciliation")
    long = match_token("reconcil", "reconciliation")
    assert short is not None
    assert long is not None
    assert short.weight < long.weight < 0.94


def test_match_evidence_is_frozen_and_rejects_unknown_fields() -> None:
    """Cross-module lexical evidence keeps the shared strict immutable boundary."""
    result = TokenMatch(weight=1.0, rule="exact", observed="x", expected="x")
    with pytest.raises(ValidationError, match="frozen"):
        result.weight = 0.0
    with pytest.raises(ValidationError, match="extra_forbidden"):
        TokenMatch.model_validate(
            {"weight": 1.0, "rule": "exact", "observed": "x", "expected": "x", "extra": "x"}
        )
