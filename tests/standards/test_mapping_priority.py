# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Whole words and whole synonyms outrank, and are never reread as, partial abbreviations."""

import pytest

from datakeel.core.standard_models import (
    BusinessSynonyms,
    ColumnProfile,
    FieldStandard,
    MappingSuggestion,
    StandardsContract,
)
from datakeel.standards.lexical import match_token
from datakeel.standards.mapping import suggest

# (column word, its whole-synonym meaning, a longer word it also abbreviates, where that word sits)
COLLISIONS = (
    ("port", "harbor", "portfolio", "label"),
    ("car", "vehicle", "carrier", "synonym"),
    ("tab", "bill", "table", "label"),
    ("plan", "scheme", "planet", "synonym"),
    ("dry", "arid", "dairy", "label"),
    ("try", "attempt", "tray", "synonym"),
    ("spend", "expenditure", "suspend", "label"),
    ("sport", "athletics", "support", "synonym"),
)


def _standard(name: str, code: str) -> FieldStandard:
    return FieldStandard(
        code=code,
        name_zh="合成业务字段",
        name_en=name,
        description="Independently generated vocabulary fixture",
        data_type="text",
        status="active",
    )


def _collision_contract(
    word: str, meaning: str, longer: str, where: str, *, own_synonym: bool = True
) -> StandardsContract:
    other = f"{longer} owner" if where == "synonym" else longer
    groups = [BusinessSynonyms(canonical=meaning, alternatives=(word,))] if own_synonym else []
    if where == "synonym":
        groups.append(BusinessSynonyms(canonical=f"{longer} owner", alternatives=(longer,)))
    return StandardsContract(
        standards=(
            _standard(meaning, "whole_meaning"),
            _standard(other, "partial_meaning"),
            _standard("geology", "distractor"),
        ),
        synonyms=tuple(groups),
    )


def _suggest(name: str, contract: StandardsContract, data_type: str = "text") -> MappingSuggestion:
    return suggest(ColumnProfile(column_id=name, name=name, data_type=data_type), contract)


def _codes(result: MappingSuggestion) -> list[str]:
    return [item.standard_code for item in result.candidates]


@pytest.mark.parametrize(("word", "meaning", "longer", "where"), COLLISIONS)
def test_whole_synonym_ranks_first_when_word_also_abbreviates_another(
    word: str, meaning: str, longer: str, where: str
) -> None:
    """Eight prefix, skeleton and deletion collisions keep the complete synonym meaning first."""
    result = _suggest(word, _collision_contract(word, meaning, longer, where))
    assert _codes(result)[:1] == ["whole_meaning"], (word, result)
    assert any("synonym" in reason.lower() for reason in result.candidates[0].reasons)


@pytest.mark.parametrize(("word", "meaning", "longer", "where"), COLLISIONS)
def test_complete_word_is_never_reread_as_abbreviation_of_another_meaning(
    word: str, meaning: str, longer: str, where: str
) -> None:
    """The colliding label or synonym never enters the candidates, even at low confidence."""
    result = _suggest(f"{word}_code", _collision_contract(word, meaning, longer, where))
    assert "partial_meaning" not in _codes(result), (word, result)


@pytest.mark.parametrize(("word", "meaning", "longer", "where"), COLLISIONS)
def test_same_word_still_abbreviates_when_it_is_not_a_contract_word(
    word: str, meaning: str, longer: str, where: str
) -> None:
    """Without its own synonym the word is free to abbreviate, so the lock is vocabulary-scoped."""
    contract = _collision_contract(word, meaning, longer, where, own_synonym=False)
    result = _suggest(word, contract)
    assert _codes(result)[:1] == ["partial_meaning"], (word, result)
    partial = match_token(word, longer)
    assert partial is not None
    assert partial.rule in {"prefix", "consonant", "subsequence"}


def test_shop_is_a_store_not_a_prefix_of_shopper(contract: StandardsContract) -> None:
    """The shipped store synonym wins and the customer shopper prefix never becomes a candidate."""
    result = _suggest("shop_id", contract, "integer")
    assert _codes(result) == ["store_id"]
    assert "Synonym: 'shop' means 'store' (shop)" in result.candidates[0].reasons


@pytest.mark.parametrize("name", ["shop_name", "shop_code", "shop", "stock_id", "stock_no"])
def test_whole_synonyms_never_leak_into_prefix_neighbours(
    contract: StandardsContract, name: str
) -> None:
    """Shop is not shopper (customer) and stock is not stockroom (warehouse)."""
    codes = _codes(_suggest(name, contract))
    assert not any(code.startswith(("customer", "warehouse")) for code in codes), (name, codes)


def test_word_may_abbreviate_a_word_of_its_own_synonym_group(contract: StandardsContract) -> None:
    """A ticket abbreviation listed as a ticket synonym still reads as ticket, not as the buyer."""
    result = _suggest("buyer_tckt_no", contract)
    assert _codes(result)[0] == "ticket_id"
    assert "Consonant: 'tckt' matches 'ticket'" in result.candidates[0].reasons


def test_closest_partial_synonym_wins_over_a_longer_listing() -> None:
    """An abbreviation takes the synonym it covers best, not the longest listed alternative."""
    contract = StandardsContract(
        standards=(_standard("alpha id", "alpha_id"), _standard("beta id", "beta_id")),
        synonyms=(
            BusinessSynonyms(canonical="alpha", alternatives=("component",)),
            BusinessSynonyms(canonical="beta", alternatives=("completion",)),
        ),
    )
    result = _suggest("comp_id", contract)
    assert _codes(result)[:1] == ["alpha_id"]
    assert "Prefix: 'comp' matches synonym 'component'" in result.candidates[0].reasons


def test_shipped_component_abbreviation_stays_a_part(contract: StandardsContract) -> None:
    """Comp is nearer component (part) than the shipped completion (end) synonym."""
    result = _suggest("comp_id", contract, "integer")
    assert _codes(result)[:1] == ["part_id"]


def test_evidence_ladder_orders_complete_before_partial_rules() -> None:
    """Exact > inflected > whole synonym > prefix or skeleton > ordered deletion, for one word."""
    contract = StandardsContract(
        standards=(_standard("harbor", "harbor"),),
        synonyms=(BusinessSynonyms(canonical="harbor", alternatives=("port",)),),
    )
    scores = {
        name: _suggest(name, contract).candidates[0].score
        for name in ("harbor", "harbors", "port", "harb", "hrbr", "harbr")
    }
    assert scores["harbor"] > scores["harbors"] > scores["port"]
    assert scores["port"] > max(scores["harb"], scores["hrbr"]) > scores["harbr"]


def test_partial_rules_never_reach_the_complete_synonym_weight() -> None:
    """Even an almost complete truncation stays below the 0.86 whole-synonym discount."""
    result = match_token("reconciliatio", "reconciliation")
    assert result is not None
    assert result.rule == "prefix"
    assert result.weight < 0.86
