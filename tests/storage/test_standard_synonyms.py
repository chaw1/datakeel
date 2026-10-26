# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Approved vocabulary survives authoritative revisions, partial edits and rollback."""

import pytest

from datakeel.actions.models import ActionContext
from datakeel.actions.service import prepare_action
from datakeel.core.errors import BudgetError
from datakeel.core.models import JsonDocument
from datakeel.core.standard_models import BusinessSynonyms, StandardsContract
from datakeel.storage.database import Database
from datakeel.storage.standard_store import get_contract, history
from tests.standards_support import approved_change, standard_contract


def _import(db: Database, contract: StandardsContract) -> None:
    approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )


def test_vocabulary_survives_approved_import_partial_edits_and_historical_replay(
    db: Database,
) -> None:
    """Field and code edits retain groups, and rollback restores prior synonym semantics."""
    email = BusinessSynonyms(canonical="email", alternatives=("mail",))
    phone = BusinessSynonyms(canonical="phone", alternatives=("mobile", "tel"))
    original = standard_contract().model_copy(update={"synonyms": (email,)})
    _import(db, original)
    assert get_contract(db).synonyms == (email,)
    field = original.standards[0].model_copy(update={"owner": "Business owner"})
    approved_change(
        db, "update_standard", JsonDocument({"definition": field.model_dump(mode="json")})
    )
    code_list = original.code_lists[0].model_copy(update={"name": "Customer states"})
    approved_change(
        db, "update_code_list", JsonDocument({"definition": code_list.model_dump(mode="json")})
    )
    assert get_contract(db).synonyms == (email,)
    _import(db, StandardsContract(synonyms=(phone,)))
    assert get_contract(db).synonyms == (email, phone)
    replacement = BusinessSynonyms(canonical="EMAIL", alternatives=("mailbox",))
    _import(db, StandardsContract(synonyms=(replacement,)))
    assert get_contract(db).synonyms == (replacement, phone)
    assert history(db).revisions[0].contract.synonyms == (email,)
    approved_change(db, "rollback_standards", JsonDocument({"revision": 1}))
    assert get_contract(db).synonyms == (email,)
    approved_change(db, "rollback_standards", JsonDocument({"revision": 0}))
    assert get_contract(db).synonyms == ()


def test_conflicting_partial_synonym_import_is_rejected_before_revision(db: Database) -> None:
    """An otherwise valid fragment cannot introduce an alias already owned by another group."""
    _import(
        db,
        StandardsContract(
            synonyms=(BusinessSynonyms(canonical="phone", alternatives=("mobile",)),)
        ),
    )
    collision = StandardsContract(
        synonyms=(BusinessSynonyms(canonical="cellphone", alternatives=("mobile",)),)
    )
    with pytest.raises(ValueError, match="Conflicting business synonym"):
        prepare_action(
            db, "import_standards", JsonDocument({"contract": collision.model_dump(mode="json")})
        )
    assert len(history(db).revisions) == 1


def test_synonym_groups_are_visible_targets_and_count_toward_impact(db: Database) -> None:
    """Vocabulary-only changes cannot bypass the action target and rollback impact limits."""
    contract = StandardsContract(
        synonyms=(
            BusinessSynonyms(canonical="email", alternatives=("mail",)),
            BusinessSynonyms(canonical="phone", alternatives=("mobile",)),
        )
    )
    params = JsonDocument({"contract": contract.model_dump(mode="json")})
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(db, "import_standards", params, ActionContext(max_objects=1))
    run = approved_change(db, "import_standards", params)
    assert run.receipt is not None
    targets = [item for item in run.receipt.outputs if item.asset_type == "standard_synonyms"]
    assert {item.asset_id for item in targets} == {"email", "phone"}
    with pytest.raises(BudgetError, match="impact exceeds"):
        prepare_action(
            db, "rollback_standards", JsonDocument({"revision": 0}), ActionContext(max_objects=1)
        )
