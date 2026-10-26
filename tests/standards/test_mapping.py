# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Human-labeled name variations and unsupported fields test semantic rule generality."""

import pytest

from datakeel.core.standard_models import ColumnProfile, FieldStandard, StandardsContract
from datakeel.standards.mapping import SUGGESTION_THRESHOLD, suggest
from datakeel.standards.names import canonical_type, name_tokens

# Labels cover Chinese, SQL aliases, camel case, abbreviations and unseen affixes.
LABELED = (
    ("cust_id", "INTEGER", "customer_id"),
    ("customer_no", "BIGINT", "customer_id"),
    ("customerNumber", "INTEGER", "customer_id"),
    ("ClientIdentifier", "INTEGER", "customer_id"),
    ("客户编号", "INTEGER", "customer_id"),
    ("客户ID", "INTEGER", "customer_id"),
    ("billingCustomerId", "INTEGER", "customer_id"),
    ("customer_name", "VARCHAR(80)", "customer_name"),
    ("custName", "TEXT", "customer_name"),
    ("客户名称", "TEXT", "customer_name"),
    ("customerEmail", "TEXT", "customer_email"),
    ("cust_email", "VARCHAR(100)", "customer_email"),
    ("客户邮箱", "TEXT", "customer_email"),
    ("customerMobile", "TEXT", "customer_phone"),
    ("cust_tel", "TEXT", "customer_phone"),
    ("客户电话", "TEXT", "customer_phone"),
    ("customerAge", "INT", "customer_age"),
    ("客户年龄", "INTEGER", "customer_age"),
    ("cust_status", "TEXT", "customer_status"),
    ("客户状态", "VARCHAR(10)", "customer_status"),
    ("customerType", "TEXT", "customer_type"),
    ("客户类型", "TEXT", "customer_type"),
    ("orderNo", "BIGINT", "order_id"),
    ("订单编号", "INTEGER", "order_id"),
    ("prodId", "INT", "product_id"),
    ("产品编号", "INTEGER", "product_id"),
    ("product_cd", "TEXT", "product_code"),
    ("商品编码", "VARCHAR(12)", "product_code"),
    ("storeNumber", "INTEGER", "store_id"),
    ("门店编号", "INTEGER", "store_id"),
    ("wh_id", "INTEGER", "warehouse_id"),
    ("仓库编号", "INTEGER", "warehouse_id"),
    ("region", "TEXT", "region"),
    ("地区", "TEXT", "region"),
    ("channel", "TEXT", "channel"),
    ("销售渠道", "TEXT", "channel"),
    ("category", "TEXT", "category"),
    ("产品类别", "TEXT", "category"),
    ("qty", "INTEGER", "quantity"),
    ("quantity", "INT", "quantity"),
    ("业务数量", "INTEGER", "quantity"),
    ("paidAmt", "NUMERIC(12,2)", "paid_amount"),
    ("实付金额", "INTEGER", "paid_amount"),
    ("refund_amt", "DECIMAL(12,2)", "refund_amount"),
    ("退款金额", "INTEGER", "refund_amount"),
    ("invoicedAmount", "INTEGER", "invoiced_amount"),
    ("开票金额", "INTEGER", "invoiced_amount"),
    ("orderDate", "TEXT", "order_date"),
    ("订单日期", "VARCHAR(10)", "order_date"),
    ("joined_dt", "TEXT", "joined_date"),
    ("产品单价", "REAL", "unit_price"),
    ("unitPrice", "INTEGER", "unit_price"),
    ("revenue", "NUMERIC(12,2)", "revenue"),
    ("营业收入", "INTEGER", "revenue"),
)


@pytest.mark.parametrize(("name", "data_type", "expected"), LABELED)
def test_mapping_labeled_names_rank_correct_standard(
    contract: StandardsContract, name: str, data_type: str, expected: str
) -> None:
    """Every labeled variation ranks its actual business meaning first."""
    result = suggest(ColumnProfile(column_id="col", name=name, data_type=data_type), contract)
    assert result.candidates[0].standard_code == expected
    assert result.candidates[0].score >= SUGGESTION_THRESHOLD
    assert all(candidate.reasons for candidate in result.candidates)


def test_mapping_evaluation_meets_declared_accuracy(contract: StandardsContract) -> None:
    """Measure top-one and top-three accuracy over more than forty independent labels."""
    hits = [
        (expected, suggest(ColumnProfile(column_id=name, name=name, data_type=data_type), contract))
        for name, data_type, expected in LABELED
    ]
    top1 = sum(result.candidates[0].standard_code == expected for expected, result in hits)
    top3 = sum(
        expected in {item.standard_code for item in result.candidates} for expected, result in hits
    )
    assert len(LABELED) >= 40
    assert top1 / len(hits) >= 0.8
    assert top3 / len(hits) >= 0.95


@pytest.mark.parametrize(
    "name",
    [
        "checksum",
        "opaqueBlob",
        "compressionRatio",
        "transientDebugFlag",
        "vectorEmbedding",
        "实验分组",
        "featureHash",
        "sessionNonce",
        "cpuUsage",
        "cacheHitRatio",
        "randomSeed",
        "renderHeight",
        "xCustomMetadata",
        "billingCycle",
        "traceparent",
    ],
)
def test_mapping_unknown_business_meaning_abstains(contract: StandardsContract, name: str) -> None:
    """A compatible physical type alone never invents a business mapping."""
    assert not suggest(
        ColumnProfile(column_id="x", name=name, data_type="TEXT"), contract
    ).candidates


def test_mapping_code_distribution_explains_support(contract: StandardsContract) -> None:
    """Reference-data hit rates contribute evidence and remain visible in reasons."""
    result = suggest(
        ColumnProfile(
            column_id="x", name="customerStatus", data_type="TEXT", values=("active", "inactive")
        ),
        contract,
    )
    assert "Code-list value hit rate: 100%" in result.candidates[0].reasons


def test_mapping_draft_or_deprecated_standards_excluded() -> None:
    """Only effective standards may be proposed for human confirmation."""
    definition = FieldStandard(
        code="id", name_zh="编号", name_en="id", description="Key", data_type="int"
    )
    assert not suggest(
        ColumnProfile(column_id="x", name="id", data_type="int"),
        StandardsContract(
            standards=(
                definition,
                definition.model_copy(update={"code": "old", "status": "deprecated"}),
            ),
        ),
    ).candidates


def test_name_rules_split_unseen_multilingual_compounds() -> None:
    """Rules normalize language and casing rather than memorize corpus identities."""
    assert name_tokens("CRMClientNumber") == frozenset({"crm", "customer", "id"})
    assert name_tokens("客户唯一编号") == frozenset({"customer", "唯一", "id"})
    assert canonical_type("TIMESTAMP WITH TIME ZONE") == "timestamp"


@pytest.mark.parametrize(
    ("name", "data_type", "values", "reason"),
    [
        ("orderDate", "TEXT", ("2026-10-27", "bad-date"), "Pattern value hit rate: 50%"),
        ("customerAge", "INTEGER", (10, 200), "Numeric range value hit rate: 50%"),
        ("customerName", "TEXT", ("Sample Person", None), "Nonempty observed value rate: 50%"),
    ],
)
def test_value_distribution_reasons_are_measured(
    contract: StandardsContract,
    name: str,
    data_type: str,
    values: tuple[str | int | None, ...],
    reason: str,
) -> None:
    """Pattern, range and null distributions contribute bounded readable evidence."""
    result = suggest(
        ColumnProfile(column_id=name, name=name, data_type=data_type, values=values), contract
    )
    assert reason in result.candidates[0].reasons


def test_distribution_match_without_name_evidence_does_not_invent_mapping(
    contract: StandardsContract,
) -> None:
    """Coincidental values do not turn an unrelated column into a known business concept."""
    assert not suggest(
        ColumnProfile(
            column_id="x",
            name="opaquePayload",
            data_type="TEXT",
            values=("active", "inactive"),
        ),
        contract,
    ).candidates


def test_incompatible_type_is_explained_without_hiding_exact_name_match(
    contract: StandardsContract,
) -> None:
    """An obvious business identity still permits confirmation and later type checking."""
    result = suggest(ColumnProfile(column_id="x", name="customer_id", data_type="TEXT"), contract)
    assert result.candidates[0].standard_code == "customer_id"
    assert "Type differs: TEXT / integer" in result.candidates[0].reasons


def test_weak_common_name_with_conflicting_type_abstains(contract: StandardsContract) -> None:
    """Weak name overlap plus incompatible type does not clear the confidence threshold."""
    assert not suggest(
        ColumnProfile(column_id="x", name="crm_cust_no", data_type="TEXT"), contract
    ).candidates


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("CUSTNO", "customer_id"),
        ("ORDERID", "order_id"),
        ("CUSTOMEREMAILADDRESS", "customer_email"),
        ("客户唯一编号", "customer_id"),
    ],
)
def test_unseen_compact_and_multilingual_identifier_names_generalize(
    contract: StandardsContract,
    name: str,
    expected: str,
) -> None:
    """Vocabulary segmentation handles unseen all-capital compounds without per-field aliases."""
    data_type = "TEXT" if expected == "customer_email" else "INTEGER"
    assert (
        suggest(ColumnProfile(column_id=name, name=name, data_type=data_type), contract)
        .candidates[0]
        .standard_code
        == expected
    )


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        ("sales_region", "TEXT", "region"),
        ("biz_qty", "INTEGER", "quantity"),
        ("sales_channel", "TEXT", "channel"),
        ("legacy_category", "TEXT", "category"),
        ("previous_revenue", "NUMERIC", "revenue"),
        ("archiveCustomerNumber", "BIGINT", "customer_id"),
        ("客户号", "INTEGER", "customer_id"),
        ("customerPrimaryKey", "INTEGER", "customer_id"),
        ("customer_pk", "INTEGER", "customer_id"),
        ("ORDERPRIMARYKEY", "INTEGER", "order_id"),
        ("工单号", "INTEGER", "ticket_id"),
        ("regionalWarehouseNumber", "INTEGER", "warehouse_id"),
    ],
)
def test_complete_specific_business_signal_tolerates_unknown_prefix(
    contract: StandardsContract,
    name: str,
    kind: str,
    expected: str,
) -> None:
    """Complete business vocabulary earns support while extra qualifiers reduce confidence."""
    assert (
        suggest(ColumnProfile(column_id=name, name=name, data_type=kind), contract)
        .candidates[0]
        .standard_code
        == expected
    )


@pytest.mark.parametrize(
    "name",
    [
        "legacy_debug_id",
        "opaque_reference_code",
        "temporary_raw_name",
        "local_cache_status",
        "system_trace_time",
        "customerDebugFlag",
        "productVector",
        "warehouseChecksum",
        "unclassifiedField",
        "unknownNameSuffix",
        "opaque_serial_number",
        "regionDistance",
    ],
)
def test_generic_or_incomplete_vocabulary_cannot_gain_prefix_bonus(
    contract: StandardsContract,
    name: str,
) -> None:
    """Generic identifiers and partial business overlap remain insufficient for a mapping."""
    assert not suggest(
        ColumnProfile(column_id=name, name=name, data_type="INTEGER"), contract
    ).candidates


def test_phone_number_suffix_does_not_turn_customer_identifier_into_phone_candidate(
    contract: StandardsContract,
) -> None:
    """Identifier normalization preserves the distinct business meaning of phone numbers."""
    assert (
        name_tokens("客户手机号")
        == name_tokens("customerPhoneNumber")
        == frozenset({"customer", "phone"})
    )
    result = suggest(ColumnProfile(column_id="x", name="crm_cust_no", data_type="TEXT"), contract)
    assert all(item.standard_code != "customer_phone" for item in result.candidates)
