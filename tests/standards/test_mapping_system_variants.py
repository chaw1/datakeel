# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent system guards and composed synonyms preserve mapping precision and recall."""

import pytest

from datakeel.core.standard_models import ColumnProfile, StandardsContract
from datakeel.standards.mapping import suggest


@pytest.mark.parametrize(
    "name",
    [
        "customer_del_flag",
        "store_dlt_flg",
        "product_is_removed",
        "warehouse_rmv_flag",
        "customer_tnt_id",
        "buyer_tnt_code",
        "customer_revision_no",
        "order_revision_id",
        "warehouse_ver_id",
        "store_vers_no",
        "store_geo_x",
        "warehouse_geo_y",
        "customer_gps_lat",
        "store_coordinate_x",
        "warehouse_coordinates_y",
        "customer_ipaddr",
        "store_ipaddress",
        "warehouse_ipv6",
        "case_sensitive_flag",
        "value_type_code",
        "customer_etl_load_dttm",
        "purchase_order_hash",
        "customer_vrsn",
        "store_rvsn",
        "customer_versioned",
        "buyer_tnnt_id",
        "product_dltd_flag",
        "warehouse_rmvd_flag",
        "store_lttd",
        "warehouse_lngtd",
        "customer_rowversion",
        "customer_recordrevision",
        "order_rowhash",
        "store_systemchecksum",
        "客户版本号",
        "客户修订号",
        "客户租户编号",
        "订单逻辑删除标志",
        "门店行哈希",
        "仓库经度",
        "门店纬度",
        "订单校验和",
        "客户调试标志",
        "商品缓存标志",
    ],
)
def test_business_named_system_variants_do_not_produce_candidates(
    contract: StandardsContract, name: str
) -> None:
    """Deletion, tenancy, revisions, coordinates and networking override apparent business hits."""
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)
    assert not result.candidates, (name, result.candidates)


@pytest.mark.parametrize(
    ("phrase", "equivalent", "expected"),
    [
        ("stock_keeping_unit", "sku", "product_code"),
        ("product_item_code", "item_code", "product_code"),
        ("mobile_tel", "mobile", "customer_phone"),
    ],
)
def test_complete_synonym_phrases_do_not_reuse_consumed_tokens(
    contract: StandardsContract, phrase: str, equivalent: str, expected: str
) -> None:
    """Long phrases and repeated equivalents retain the same undiluted business signal."""
    composed = suggest(ColumnProfile(column_id="x", name=phrase, data_type="text"), contract)
    simple = suggest(ColumnProfile(column_id="x", name=equivalent, data_type="text"), contract)
    assert composed.candidates[0].standard_code == expected
    assert composed.candidates[0].score == simple.candidates[0].score


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("service_requests_id", "ticket_id"),
        ("support_requests_no", "ticket_id"),
        ("buyer_mailboxes", "customer_email"),
        ("mailboxes", "customer_email"),
        ("settlement_value", "paid_amount"),
        ("reimbursements_amount", "refund_amount"),
    ],
)
def test_word_forms_compose_with_contract_synonym_phrases(
    contract: StandardsContract, name: str, expected: str
) -> None:
    """Inflected synonym alternatives generalize without adding their spellings to YAML."""
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)
    assert result.candidates[0].standard_code == expected, (name, result.candidates)
    reasons = " ".join(result.candidates[0].reasons).lower()
    assert "synonym" in reasons
    assert "morphology" in reasons


def test_generic_value_does_not_create_competing_business_meaning(
    contract: StandardsContract,
) -> None:
    """A generic token beside turnover must not manufacture independent amount evidence."""
    result = suggest(
        ColumnProfile(column_id="x", name="turnover_value", data_type="decimal"), contract
    )
    assert [item.standard_code for item in result.candidates] == ["revenue"]


@pytest.mark.parametrize("name", ["rev_amt", "rvn_amt", "revenue_amount"])
def test_revenue_abbreviations_do_not_become_revision_system_markers(
    contract: StandardsContract, name: str
) -> None:
    """Only complete system skeletons override revenue's distinct business abbreviations."""
    result = suggest(ColumnProfile(column_id="x", name=name, data_type="number"), contract)
    assert result.candidates[0].standard_code == "revenue"


def test_complete_version_skeleton_overrides_a_business_prefix(contract: StandardsContract) -> None:
    """A new version consonant skeleton never turns the customer prefix into a mapping."""
    result = suggest(ColumnProfile(column_id="x", name="customer_vrsn", data_type="text"), contract)
    assert not result.candidates


def test_business_meaning_outweighs_a_shared_measure_suffix(contract: StandardsContract) -> None:
    """An amount suffix cannot outrank the observed revenue business abbreviation."""
    result = suggest(ColumnProfile(column_id="x", name="rev_amt", data_type="number"), contract)
    assert [item.standard_code for item in result.candidates] == ["revenue"]


def test_chinese_system_words_override_customer_business_prefix(
    contract: StandardsContract,
) -> None:
    """Chinese system metadata is normalized before considering its apparent business prefix."""
    result = suggest(ColumnProfile(column_id="x", name="客户版本号", data_type="text"), contract)
    assert not result.candidates
