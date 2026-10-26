# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Business vocabulary is explicit, unambiguous and portable across contract fragments."""

from pathlib import Path

import pytest
from pydantic import ValidationError as ModelValidationError

from datakeel.core.errors import ValidationError
from datakeel.core.standard_models import BusinessSynonyms, StandardsContract
from datakeel.standards.loader import dump_contract, load_contract


@pytest.mark.parametrize(
    "group",
    [
        {"canonical": " ", "alternatives": ["mail"]},
        {"canonical": "email", "alternatives": ["\t"]},
        {"canonical": "email", "alternatives": []},
        {"canonical": "email", "alternatives": [" EMAIL "]},
        {"canonical": "email", "alternatives": ["mail", " MAIL "]},
        {"canonical": "product code", "alternatives": ["product  code"]},
        {"canonical": "email", "alternatives": ["mail"], "unknown": True},
    ],
)
def test_synonym_groups_reject_empty_duplicate_and_unknown_terms(group: dict[str, object]) -> None:
    """Whitespace and casing cannot hide empty or repeated business identities."""
    with pytest.raises(ModelValidationError):
        BusinessSynonyms.model_validate(group)


@pytest.mark.parametrize(
    "second",
    [
        BusinessSynonyms(canonical=" EMAIL ", alternatives=("electronic mail",)),
        BusinessSynonyms(canonical="mail", alternatives=("electronic mail",)),
        BusinessSynonyms(canonical="electronic mail", alternatives=("Mail",)),
    ],
)
def test_synonym_terms_cannot_resolve_to_conflicting_groups(second: BusinessSynonyms) -> None:
    """Canonical and alternative terms share one case-insensitive namespace."""
    first = BusinessSynonyms(canonical="email", alternatives=("mail",))
    with pytest.raises(ModelValidationError, match="Conflicting business synonym"):
        StandardsContract(synonyms=(first, second))


def test_directory_synonyms_roundtrip_and_reject_cross_file_conflicts(tmp_path: Path) -> None:
    """Directory fragments preserve complete groups and reject ambiguous merged vocabulary."""
    first = tmp_path / "first.yaml"
    first.write_text("synonyms: [{canonical: phone, alternatives: [mobile, tel]}]")
    contract = load_contract(tmp_path)
    assert contract.synonyms == (
        BusinessSynonyms(canonical="phone", alternatives=("mobile", "tel")),
    )
    exported = tmp_path / "export.yaml"
    exported.write_text(dump_contract(contract))
    assert load_contract(exported) == contract
    with pytest.raises(ValidationError, match="Conflicting business synonym"):
        load_contract(tmp_path)


def test_shipped_business_vocabulary_is_in_loaded_contract(contract: StandardsContract) -> None:
    """Default vocabulary ships as extensible data rather than a Python alias registry."""
    groups = {group.canonical: group.alternatives for group in contract.synonyms}
    assert "mail" in groups["email"]
    assert {"mobile", "tel"} <= set(groups["phone"])
    assert {"shop", "outlet"} <= set(groups["store"])
    assert "sku" in groups["product code"]
    assert "tkt" in groups["ticket"]


def test_legacy_contract_defaults_to_empty_vocabulary() -> None:
    """Existing serialized revisions remain readable without a vocabulary declaration."""
    assert StandardsContract.model_validate({"standards": [], "code_lists": []}).synonyms == ()
