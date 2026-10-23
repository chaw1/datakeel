# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Contract resources and typed extraction contexts remain reproducible in a wheel."""

from pathlib import Path

import pytest

from datakeel.core.models import FileItem
from datakeel.operators.evidence import contracts
from datakeel.operators.evidence.common import subject


def test_contracts_when_loaded_have_fixed_parameters_and_content_hashes() -> None:
    """Verify the threshold, blocking width, and semantic aliases have one source."""
    contract = contracts.read_near_duplicate()
    assert (contract.bits, contract.prefix_bits, contract.hamming_threshold) == (64, 4, 8)
    assert [concept.id for concept in contracts.read_lexicon().concepts] == [
        "person",
        "car",
        "night",
        "rain",
        "indoor",
    ]
    assert all(len(digest) == 64 for digest in contracts.contract_hashes())


def test_contract_path_when_checkout_missing_uses_packaged_resource(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verify wheel installations do not rely on the source repository path."""
    monkeypatch.setattr(contracts, "PACKAGE_ROOT", tmp_path / "package")
    assert (
        contracts.contract_path("lexicon.yaml")
        == tmp_path / "package/_contracts/evidence/lexicon.yaml"
    )


def test_subject_when_version_missing_rejects_observation(sample: FileItem) -> None:
    """Verify extractors cannot silently anchor facts to an unversioned asset."""
    altered = sample.model_copy(update={"metadata": {"evidence_subject": {"asset_id": sample.id}}})
    with pytest.raises(ValueError, match="version"):
        subject(altered)
