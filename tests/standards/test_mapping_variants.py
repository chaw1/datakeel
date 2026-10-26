# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Unregistered variants exercise lexical rules independently of enterprise aliases."""

import pytest

from datakeel.core.standard_models import (
    BusinessSynonyms,
    ColumnProfile,
    FieldStandard,
    MappingCandidate,
    StandardsContract,
)
from datakeel.standards.mapping import SUGGESTION_THRESHOLD, suggest

PREFIX_CASES = (
    ("reconc", "reconciliation"),
    ("fulf", "fulfillment"),
    ("consig", "consignment"),
    ("rese", "reservation"),
    ("receiv", "receivable"),
    ("procur", "procurement"),
)
MORPHOLOGY_CASES = (
    ("invoiced", "invoice"),
    ("shipping", "ship"),
    ("paid", "payment"),
    ("approved", "approve"),
    ("delivered", "deliver"),
    ("allocation", "allocate"),
    ("discounts", "discount"),
    ("dispatches", "dispatch"),
)
SPELLING_CASES = (
    ("colour", "color"),
    ("flavour", "flavor"),
    ("behaviour", "behavior"),
    ("authorise", "authorize"),
    ("catalogue", "catalog"),
    ("centre", "center"),
    ("metre", "meter"),
    ("organise", "organize"),
)
CONSONANT_CASES = (
    ("dscnt", "discount"),
    ("spplr", "supplier"),
    ("prchs", "purchase"),
    ("shpmnt", "shipment"),
    ("rcpt", "receipt"),
    ("wrnty", "warranty"),
)
SYNONYM_CASES = (
    ("buyer", "customer"),
    ("outlet", "store"),
    ("stock", "inventory"),
    ("reimbursement", "refund"),
    ("voucher", "coupon"),
    ("consignment", "shipment"),
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


def _candidate(
    observed: str, expected: str, synonyms: tuple[BusinessSynonyms, ...] = ()
) -> MappingCandidate:
    contract = StandardsContract(
        standards=(
            _standard(expected),
            _standard("geology", "distractor_one"),
            _standard("neutron", "distractor_two"),
        ),
        synonyms=synonyms,
    )
    result = suggest(ColumnProfile(column_id="x", name=observed, data_type="text"), contract)
    assert result.candidates, (observed, expected)
    candidate = result.candidates[0]
    assert candidate.standard_code == "target", (observed, expected, result)
    assert candidate.reasons
    return candidate


def _assert_explained_variant(observed: str, expected: str, rule: str) -> None:
    candidate = _candidate(observed, expected)
    explanation = " ".join(candidate.reasons).lower()
    assert observed in explanation
    assert expected in explanation
    assert rule in explanation
    assert candidate.score < _candidate(expected, expected).score


@pytest.mark.parametrize(("observed", "expected"), PREFIX_CASES)
def test_unregistered_prefixes_recover_custom_business_words(observed: str, expected: str) -> None:
    """Six previously unregistered truncations recover standards outside the shipped corpus."""
    _assert_explained_variant(observed, expected, "prefix")


@pytest.mark.parametrize(("observed", "expected"), MORPHOLOGY_CASES)
def test_regular_and_irregular_word_forms_recover_custom_standards(
    observed: str, expected: str
) -> None:
    """Inflection, derivation and irregular payment forms use discounted root evidence."""
    _assert_explained_variant(observed, expected, "morphology")


@pytest.mark.parametrize(("observed", "expected"), SPELLING_CASES)
def test_systematic_british_spelling_recovers_custom_american_standards(
    observed: str, expected: str
) -> None:
    """Four spelling families generalize beyond words appearing in enterprise standards."""
    _assert_explained_variant(observed, expected, "spelling")


@pytest.mark.parametrize(("observed", "expected"), CONSONANT_CASES)
def test_unregistered_consonant_skeletons_recover_custom_standards(
    observed: str, expected: str
) -> None:
    """Consonant preservation, repeated letters and silent vowels need no alias entries."""
    _assert_explained_variant(observed, expected, "consonant")


@pytest.mark.parametrize(("observed", "expected"), SYNONYM_CASES)
def test_contract_business_synonyms_recover_custom_standards_with_discount(
    observed: str, expected: str
) -> None:
    """Contract extensions supply six cross-domain equivalences without changing token code."""
    synonyms = (BusinessSynonyms(canonical=expected, alternatives=(observed,)),)
    candidate = _candidate(observed, expected, synonyms)
    explanation = " ".join(candidate.reasons).lower()
    assert observed in explanation
    assert expected in explanation
    assert "synonym" in explanation
    assert candidate.score < _candidate(expected, expected, synonyms).score


@pytest.mark.parametrize(
    ("observed", "expected", "rule"),
    [
        *((left, right, "prefix") for left, right in PREFIX_CASES),
        *((left, right, "morphology") for left, right in MORPHOLOGY_CASES),
        *((left, right, "spelling") for left, right in SPELLING_CASES),
        *((left, right, "consonant") for left, right in CONSONANT_CASES),
        *((left, right, "synonym") for left, right in SYNONYM_CASES),
    ],
)
def test_novel_compounds_preserve_variant_business_signal(
    observed: str, expected: str, rule: str
) -> None:
    """Unknown prefixes and generic suffixes preserve each of the five kinds of evidence."""
    synonyms = (
        (BusinessSynonyms(canonical=expected, alternatives=(observed,)),)
        if rule == "synonym"
        else ()
    )
    candidate = _candidate(f"archive_{observed}_code", f"{expected} code", synonyms)
    explanation = " ".join(candidate.reasons).lower()
    assert observed in explanation
    assert expected in explanation
    assert rule in explanation
    exact = _candidate(f"archive_{expected}_code", f"{expected} code", synonyms)
    assert candidate.score < exact.score


@pytest.mark.parametrize(
    ("observed", "expected"),
    [("mail", "customer_email"), ("sku", "product_code"), ("tkt_id", "ticket_id")],
)
def test_shipped_business_synonyms_include_phrases_and_ticket_abbreviations(
    contract: StandardsContract, observed: str, expected: str
) -> None:
    """The real YAML vocabulary supports common domain synonyms and multiword SKU meaning."""
    result = suggest(ColumnProfile(column_id="x", name=observed, data_type="text"), contract)
    assert result.candidates
    assert result.candidates[0].standard_code == expected


@pytest.mark.parametrize(
    "name",
    [
        "etl_loaded_at",
        "etl_updated_ts",
        "etl_batch_id",
        "dw_ingested_time",
        "row_hash",
        "row_checksum",
        "record_sha256",
        "customer_row_hash",
        "order_etl_timestamp",
        "soft_delete_flag",
        "is_deleted",
        "del_flg",
        "customer_deleted_flag",
        "tenant_id",
        "tenant_code",
        "organization_tenant_id",
        "row_version",
        "record_version_no",
        "version_number",
        "customer_version",
        "latitude",
        "longitude",
        "geo_lat",
        "geo_lng",
        "store_latitude",
        "warehouse_longitude",
        "id",
        "no",
        "code",
        "name",
        "type",
        "flag",
        "ts",
        "hash",
        "json",
        "ip",
        "version",
        "external_id",
        "legacy_name",
        "payload_json",
        "unknown_flag",
    ],
)
def test_system_and_generic_columns_never_acquire_business_suggestions(
    contract: StandardsContract, name: str
) -> None:
    """Forty-one system and generic negatives protect the precision of expanded recall."""
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)
    assert not result.candidates, (name, result.candidates)


def test_partial_business_hit_keeps_three_low_confidence_candidates() -> None:
    """One novel truncation retains reviewable alternatives below the acceptance threshold."""
    contract = StandardsContract(
        standards=tuple(
            _standard(f"reconciliation {word}", f"candidate_{index}")
            for index, word in enumerate(("date", "amount", "status", "result"))
        )
    )
    result = suggest(ColumnProfile(column_id="x", name="reconc", data_type="text"), contract)
    assert len(result.candidates) == 3
    assert all(candidate.score < SUGGESTION_THRESHOLD for candidate in result.candidates)
    assert all(candidate.low_confidence for candidate in result.candidates)
    assert all("prefix" in " ".join(candidate.reasons).lower() for candidate in result.candidates)


def test_contract_synonyms_are_scoped_to_the_supplied_snapshot() -> None:
    """A configured equivalence cannot leak into a later independently supplied contract."""
    standard = _standard("coupon")
    profile = ColumnProfile(column_id="x", name="voucher", data_type="text")
    synonym = BusinessSynonyms(canonical="coupon", alternatives=("voucher",))
    configured = suggest(profile, StandardsContract(standards=(standard,), synonyms=(synonym,)))
    assert configured.candidates
    assert not suggest(profile, StandardsContract(standards=(standard,))).candidates


def test_prefix_rule_is_required_for_unregistered_truncation() -> None:
    """A measured standalone assertion kills a disabled prefix mechanism."""
    _assert_explained_variant("procur", "procurement", "prefix")


def test_morphology_rule_is_required_for_irregular_payment() -> None:
    """A measured standalone assertion kills a disabled root-normalization mechanism."""
    _assert_explained_variant("paid", "payment", "morphology")


def test_spelling_rule_is_required_for_british_colour() -> None:
    """A measured standalone assertion kills a disabled spelling mechanism."""
    _assert_explained_variant("colour", "color", "spelling")


def test_consonant_rule_is_required_for_supplier_skeleton() -> None:
    """A measured standalone assertion kills a disabled consonant mechanism."""
    _assert_explained_variant("spplr", "supplier", "consonant")


def test_synonym_rule_is_required_for_contract_extension() -> None:
    """A measured standalone assertion kills ignored business vocabulary snapshots."""
    synonym = BusinessSynonyms(canonical="coupon", alternatives=("voucher",))
    candidate = _candidate("voucher", "coupon", (synonym,))
    assert "synonym" in " ".join(candidate.reasons).lower()


def test_synonym_weight_stays_below_an_exact_business_name() -> None:
    """A measured standalone assertion kills removal of the synonym confidence discount."""
    synonym = BusinessSynonyms(canonical="coupon", alternatives=("voucher",))
    candidate = _candidate("voucher", "coupon", (synonym,))
    exact = _candidate("coupon", "coupon", (synonym,))
    assert candidate.score < exact.score


def test_generic_guard_rejects_a_custom_exact_generic_standard() -> None:
    """An exact generic field identity alone still lacks a business meaning."""
    profile = ColumnProfile(column_id="x", name="code", data_type="text")
    assert not suggest(profile, StandardsContract(standards=(_standard("code"),))).candidates


def test_system_guard_overrides_an_exact_business_named_system_standard() -> None:
    """An exact system identity must not gain legitimacy from words such as customer."""
    profile = ColumnProfile(column_id="x", name="customer_row_hash", data_type="text")
    contract = StandardsContract(standards=(_standard("customer row hash"),))
    assert not suggest(profile, contract).candidates
