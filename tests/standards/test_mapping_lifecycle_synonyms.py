# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Shipped lifecycle-date and status-verb synonyms generalize while audit columns stay unmapped."""

import pytest

from datakeel.core.standard_models import ColumnProfile, FieldStandard, StandardsContract
from datakeel.standards.lexical import match_token
from datakeel.standards.mapping import suggest

CUSTOM_STANDARDS = (
    ("end date", "end_date"),
    ("cancel reason", "cancel_reason"),
    ("approve date", "approve_date"),
    ("reject reason", "reject_reason"),
    ("close date", "close_date"),
    ("suspend date", "suspend_date"),
    ("update count", "update_count"),
    ("update date", "update_date"),
)


def _lifecycle(contract: StandardsContract) -> StandardsContract:
    """Add custom lifecycle standards beside the shipped vocabulary snapshot."""
    custom = tuple(
        FieldStandard(
            code=code,
            name_zh="合成生命周期字段",
            name_en=name,
            description="Independently generated lifecycle fixture",
            data_type="string",
            status="active",
        )
        for name, code in CUSTOM_STANDARDS
    )
    return StandardsContract(standards=custom, synonyms=contract.synonyms)


def _top(contract: StandardsContract, name: str) -> str:
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), contract)
    assert result.candidates, name
    return result.candidates[0].standard_code


@pytest.mark.parametrize(
    "name",
    [
        "begin_dt",
        "commence_date",
        "kickoff_date",
        "go_live_date",
        "inception_dt",
        "onset_date",
        "beginning_date",
        "contract_commencement_date",
    ],
)
def test_start_verbs_reach_the_shipped_start_date(contract: StandardsContract, name: str) -> None:
    """Begin, commence and related verbs and inflections reach start_date first."""
    assert _top(contract, name) == "start_date"


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("finish_date", "end_date"),
        ("expiry_dt", "end_date"),
        ("termination_date", "end_date"),
        ("voided_reason", "cancel_reason"),
        ("revoked_reason", "cancel_reason"),
        ("authorised_date", "approve_date"),
        ("accepted_date", "approve_date"),
        ("declined_reason", "reject_reason"),
        ("denied_reason", "reject_reason"),
        ("resolved_date", "close_date"),
        ("paused_date", "suspend_date"),
        ("amendment_count", "update_count"),
    ],
)
def test_status_and_lifecycle_verbs_generalize_to_custom_standards(
    contract: StandardsContract, name: str, expected: str
) -> None:
    """Each shipped verb group maps inflected and respelled forms with a synonym explanation."""
    lifecycle = _lifecycle(contract)
    result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), lifecycle)
    assert result.candidates[0].standard_code == expected, (name, result.candidates)
    assert any("Synonym:" in reason for reason in result.candidates[0].reasons)


@pytest.mark.parametrize(
    "name",
    [
        "updated_by",
        "created_at",
        "modified_by",
        "modified_date",
        "last_modified",
        "changed_at",
        "edited_ts",
        "inserted_at",
        "customer_updated_by",
        "store_last_updated",
        "order_modified_date",
        "created_by_customer_id",
        "update_date",
        "amended_by",
    ],
)
def test_audit_columns_stay_unmapped_despite_update_synonyms(
    contract: StandardsContract, name: str
) -> None:
    """Who maintained a record, and when, are system facts in shipped and custom contracts."""
    for snapshot in (contract, _lifecycle(contract)):
        result = suggest(ColumnProfile(column_id=name, name=name, data_type="text"), snapshot)
        assert not result.candidates, (name, result.candidates)


def test_modified_audit_date_is_not_an_order_date(contract: StandardsContract) -> None:
    """A measured standalone assertion kills dropping modified from the audit verbs."""
    profile = ColumnProfile(column_id="x", name="order_modified_date", data_type="text")
    assert not suggest(profile, contract).candidates


def test_audit_author_suffix_blocks_business_prefix(contract: StandardsContract) -> None:
    """A measured standalone assertion kills dropping 'by' from the audit companions."""
    profile = ColumnProfile(column_id="x", name="customer_updated_by", data_type="text")
    assert not suggest(profile, contract).candidates


@pytest.mark.parametrize(
    ("observed", "expected"),
    [("modified", "modify"), ("denied", "deny"), ("verified", "verify"), ("applied", "apply")],
)
def test_y_to_ied_inflections_share_a_root(observed: str, expected: str) -> None:
    """Past tenses that turn a final y into ied normalize like other regular inflections."""
    result = match_token(observed, expected)
    assert result is not None
    assert result.rule == "morphology"
