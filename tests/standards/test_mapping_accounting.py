# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual accounting vocabulary separates invoices from receipts and remains extensible."""

from pathlib import Path

import pytest

from datakeel.core.standard_models import (
    BusinessSynonyms,
    ColumnProfile,
    FieldStandard,
    MappingSuggestion,
    StandardsContract,
)
from datakeel.standards.loader import dump_contract, load_contract
from datakeel.standards.mapping import suggest
from datakeel.standards.names import name_tokens


def _suggest(name: str, contract: StandardsContract) -> MappingSuggestion:
    return suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)


def _receipt_contract(contract: StandardsContract) -> StandardsContract:
    fields = tuple(
        FieldStandard(
            code=code,
            name_zh=chinese,
            name_en=english,
            description="Generated accounting document fixture",
            data_type="string",
            status="active",
        )
        for code, chinese, english in (
            ("receipt_no", "收据编号", "Receipt number"),
            ("invoice_no", "发票编号", "Invoice number"),
        )
    )
    return StandardsContract(standards=fields, synonyms=contract.synonyms)


@pytest.mark.parametrize(
    "name", ["billed_amount", "bill_amt", "billing_amount", "账单金额", "发票金额", "票据金额"]
)
def test_billing_names_reach_the_shipped_invoiced_amount(
    contract: StandardsContract, name: str
) -> None:
    """Both languages recover the approved invoice amount ahead of other amount standards."""
    result = _suggest(name, contract)
    assert result.candidates
    assert result.candidates[0].standard_code == "invoiced_amount"


def test_billing_synonym_group_reaches_invoiced_amount(contract: StandardsContract) -> None:
    """The billing equivalence is required rather than a coincidental lexical abbreviation."""
    result = _suggest("billed_amount", contract)
    assert result.candidates
    assert result.candidates[0].standard_code == "invoiced_amount"
    assert any("Synonym:" in reason for reason in result.candidates[0].reasons)


def test_chinese_bill_name_reaches_invoiced_amount(contract: StandardsContract) -> None:
    """A Chinese bill name needs its explicit invoice normalization to produce the right target."""
    assert name_tokens("账单金额") == frozenset({"invoice", "amount"})
    result = _suggest("账单金额", contract)
    assert result.candidates
    assert result.candidates[0].standard_code == "invoiced_amount"


@pytest.mark.parametrize("name", ["receipt_no", "收据号", "小票编号", "rcpt_no"])
def test_receipt_names_never_suggest_invoice_fields(contract: StandardsContract, name: str) -> None:
    """A receipt keeps its own meaning when invoice and receipt standards are both available."""
    result = _suggest(name, _receipt_contract(contract))
    assert [candidate.standard_code for candidate in result.candidates] == ["receipt_no"]


def test_custom_receipt_synonym_roundtrips_beside_shipped_accounting_groups(
    contract: StandardsContract, tmp_path: Path
) -> None:
    """User vocabulary extensions remain contract data through export and subsequent import."""
    receipt = _receipt_contract(contract)
    groups = tuple(
        BusinessSynonyms(canonical="receipt", alternatives=(*group.alternatives, "till slip"))
        if group.canonical == "receipt"
        else group
        for group in receipt.synonyms
    )
    extended = StandardsContract(standards=receipt.standards, synonyms=groups)
    exported = tmp_path / "accounting.yaml"
    exported.write_text(dump_contract(extended), encoding="utf-8")
    imported = load_contract(exported)
    assert imported == extended
    result = _suggest("till_slip_no", imported)
    assert [candidate.standard_code for candidate in result.candidates] == ["receipt_no"]
    assert not _suggest("till_slip_no", receipt).candidates


def test_ambiguous_inv_is_not_a_fixed_invoice_alias() -> None:
    """Inv can abbreviate inventory too, so normalization leaves its contract-dependent meaning."""
    assert name_tokens("inv_amount") == frozenset({"inv", "amount"})


def test_billing_cycle_abstains_from_amount_but_reaches_a_custom_cycle(
    contract: StandardsContract,
) -> None:
    """An invoice synonym does not turn an explicit billing cycle into a money amount."""
    assert not _suggest("billingCycle", contract).candidates
    cycle = FieldStandard(
        code="invoice_cycle",
        name_zh="开票周期",
        name_en="Invoice cycle",
        description="Generated accounting cycle fixture",
        data_type="string",
        status="active",
    )
    custom = StandardsContract(
        standards=(*contract.standards, cycle),
        code_lists=contract.code_lists,
        synonyms=contract.synonyms,
    )
    result = _suggest("billingCycle", custom)
    assert [candidate.standard_code for candidate in result.candidates] == ["invoice_cycle"]


def _single_field_contract(code: str) -> StandardsContract:
    return StandardsContract(
        standards=(
            FieldStandard(
                code=code,
                name_zh="生成测试字段",
                name_en=code.replace("_", " "),
                description="Generated contextual qualifier fixture",
                data_type="string",
                status="active",
            ),
        )
    )


def test_date_time_qualifiers_remain_mapping_candidates() -> None:
    """Time and date retain the shared business meaning in both mapping directions."""
    for observed, expected in (
        ("order_time", "order_date"),
        ("start_time", "start_date"),
        ("order_date", "order_time"),
        ("start_date", "start_time"),
        ("invoice_cycle", "invoice_date"),
        ("invoice_status", "invoice_time"),
    ):
        result = _suggest(observed, _single_field_contract(expected))
        assert [item.standard_code for item in result.candidates] == [expected], (
            observed,
            expected,
        )


@pytest.mark.parametrize(
    ("observed", "expected"),
    [
        ("paid_date", "paid_amount"),
        ("paid_amount", "paid_date"),
        ("invoice_cycle", "invoice_amount"),
        ("invoice_status", "invoice_amount"),
        ("invoice_time", "invoice_amount"),
    ],
)
def test_amount_remains_incompatible_with_other_explicit_contexts(
    observed: str, expected: str
) -> None:
    """A shared business word cannot turn a date, time, cycle or status into an amount."""
    assert not _suggest(observed, _single_field_contract(expected)).candidates
