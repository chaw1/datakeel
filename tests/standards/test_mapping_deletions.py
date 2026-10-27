# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Ordered-deletion abbreviations recover unregistered words without admitting ordinary words."""

import pytest

from datakeel.core.standard_models import (
    ColumnProfile,
    FieldStandard,
    MappingCandidate,
    StandardsContract,
)
from datakeel.standards.lexical import match_token
from datakeel.standards.mapping import suggest

# None of these spellings is an alias, synonym or registered abbreviation anywhere in the repo.
DELETIONS = (
    ("chanl", "channel"),
    ("budgt", "budget"),
    ("custmr", "customer"),
    ("labr", "labor"),
    ("warhse", "warehouse"),
    ("delvry", "delivery"),
    ("transctn", "transaction"),
    ("balnc", "balance"),
    ("vendr", "vendor"),
    ("whse", "warehouse"),
)
# Ordinary words inside longer ones, low consonant coverage, a lost final consonant or initial.
NOT_DELETIONS = (
    ("fish", "finish"),
    ("rest", "request"),
    ("king", "keeping"),
    ("cent", "client"),
    ("tag", "target"),
    ("note", "notice"),
    ("shed", "shipped"),
    ("native", "narrative"),
    ("cusr", "customer"),
    ("depmt", "department"),
    ("govt", "government"),
    ("custm", "customer"),
    ("ustmr", "customer"),
    ("rg", "region"),
)


def _standard(name: str, code: str = "target") -> FieldStandard:
    return FieldStandard(
        code=code,
        name_zh="合成业务字段",
        name_en=name,
        description="Independently generated vocabulary fixture",
        data_type="text",
        status="active",
    )


def _top(observed: str, expected: str) -> MappingCandidate:
    contract = StandardsContract(
        standards=(_standard(expected), _standard("geology", "distractor"))
    )
    result = suggest(ColumnProfile(column_id="x", name=observed, data_type="text"), contract)
    assert result.candidates, (observed, expected)
    assert result.candidates[0].standard_code == "target", (observed, result)
    return result.candidates[0]


@pytest.mark.parametrize(("observed", "expected"), DELETIONS)
def test_ordered_deletion_keeps_initial_and_matches_with_discount(
    observed: str, expected: str
) -> None:
    """Ten unregistered vowel-dropping abbreviations match with a bounded subsequence weight."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "subsequence"
    assert 0.6 <= result.weight <= 0.64


@pytest.mark.parametrize(("observed", "expected"), NOT_DELETIONS)
def test_ordinary_or_weak_subsequences_are_not_abbreviations(observed: str, expected: str) -> None:
    """Fourteen subsequences fail the vowel-join, coverage, final, initial or length limits."""
    assert match_token(observed, expected) is None


@pytest.mark.parametrize(("observed", "expected"), DELETIONS)
def test_ordered_deletion_maps_unseen_standard_and_explains_rule(
    observed: str, expected: str
) -> None:
    """Mapping names the rule and both words and scores below the complete word."""
    candidate = _top(f"{observed}_code", f"{expected} code")
    explanation = " ".join(candidate.reasons).lower()
    assert f"subsequence: '{observed}' matches '{expected}'" in explanation
    assert candidate.score < _top(f"{expected}_code", f"{expected} code").score


def test_deletion_rule_is_required_for_unregistered_channel() -> None:
    """A measured standalone assertion kills a disabled ordered-deletion mechanism."""
    candidate = _top("chanl", "channel")
    assert "Subsequence: 'chanl' matches 'channel'" in candidate.reasons


def test_deletion_requires_a_dropped_vowel_between_kept_consonants() -> None:
    """Fish keeps its own spelling inside finish, so it is a word rather than an abbreviation."""
    assert match_token("fish", "finish") is None


def test_deletion_requires_most_consonants() -> None:
    """Keeping four of seven department consonants is too little evidence."""
    assert match_token("depmt", "department") is None


def test_deletion_ranks_below_prefix_and_consonant_skeleton() -> None:
    """The weakest rule never outranks a truncation or skeleton of the same word."""
    deletion = match_token("chanl", "channel")
    prefix = match_token("chan", "channel")
    skeleton = match_token("chnl", "channel")
    assert deletion is not None
    assert prefix is not None
    assert skeleton is not None
    assert (prefix.rule, skeleton.rule) == ("prefix", "consonant")
    assert deletion.weight < min(prefix.weight, skeleton.weight)


@pytest.mark.parametrize(
    "name",
    [
        "regn_tenant_id",
        "chanl_version",
        "custmr_row_hash",
        "budgt_deleted_flag",
        "whse_latitude",
        "labr_etl_loaded_at",
        "custmr_etl_batch_id",
        "vendr_debug_flag",
        "fish_id",
        "rest_code",
        "king_name",
        "cent_value",
        "shed_no",
        "note_type",
        "tag_code",
        "sort_key",
    ],
)
def test_deletion_rule_adds_no_system_or_generic_candidates(
    contract: StandardsContract, name: str
) -> None:
    """System guards still win over deletions, and ordinary words stay unmapped."""
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)
    assert not result.candidates, (name, result.candidates)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("regn", "region"),
        ("chanl", "channel"),
        ("budgt", "budget"),
        ("custmr_name", "customer_name"),
        ("whse_id", "warehouse_id"),
        ("labr_cost", "labor_cost"),
    ],
)
def test_deletions_reach_shipped_enterprise_standards(
    contract: StandardsContract, name: str, expected: str
) -> None:
    """The real contract recovers six unregistered deletion spellings as top-1."""
    kind = (
        "integer"
        if name.endswith("_id")
        else "number"
        if expected[-4:] in {"cost", "dget"}
        else "text"
    )
    result = suggest(ColumnProfile(column_id=name, name=name, data_type=kind), contract)
    assert result.candidates[0].standard_code == expected, (name, result.candidates)
