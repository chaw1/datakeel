# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Golden resolution tests assert preserved semantic fields for every fixture."""

import json
import subprocess
import sys
from pathlib import Path
from typing import TypedDict

import jsonschema
import pytest
import yaml
from pydantic import JsonValue

from datakeel.semantic import classify, get_contract, resolve, validate_contract


class GoldenCase(TypedDict):
    """Describe one declared semantic resolution input and expected field set."""

    caseId: str
    input: dict[str, JsonValue]
    expected: dict[str, JsonValue]


ROOT = Path(__file__).resolve().parents[2]
CORPUS = [
    json.loads(line)
    for line in (ROOT / "contracts/semantic/golden-corpus.jsonl").read_text().splitlines()
]


@pytest.mark.parametrize("case", CORPUS, ids=lambda case: case["caseId"])
def test_golden(case: GoldenCase) -> None:
    """Verify golden."""
    actual = resolve(case["input"])
    assert {key: actual.get(key) for key in case["expected"]} == case["expected"]


def test_contract_integrity() -> None:
    """Verify contract integrity."""
    contract = get_contract()
    assert len(contract["formats"]) == 40
    assert sum(len(item["extensions"]) for item in contract["formats"]) == 213
    assert len(CORPUS) == 211
    assert contract.root == yaml.safe_load(
        (ROOT / "contracts/semantic/file-semantics.yaml").read_text()
    )
    validate_contract(contract)
    jsonschema.validate(
        contract.root,
        json.loads((ROOT / "contracts/semantic/file-semantics.schema.json").read_text()),
    )
    contract["formats"].append(contract["formats"][0])
    with pytest.raises(ValueError, match="Duplicate format"):
        validate_contract(contract)


def test_generated_snapshots_current() -> None:
    """Verify generated snapshots current."""
    paths = [
        ROOT / "datakeel/semantic/_snapshot.py",
        ROOT / "datakeel/semantic/snapshot.ts",
        ROOT / "datakeel/semantic/_snapshot.json",
    ]
    before = [path.read_bytes() for path in paths]
    subprocess.run([sys.executable, "scripts/generate_semantic.py"], cwd=ROOT, check=True)
    assert before == [path.read_bytes() for path in paths]


def test_admission_and_compound_suffix() -> None:
    """Verify admission and compound suffix."""
    assert classify("scan.nii.gz")["format_code"] == "nifti"
    assert classify("a.jpg")["admission_status"] == "accepted"
    assert classify("a.exe")["admission_status"] == "rejected"
    assert classify("a.unrecognized")["admission_status"] == "quarantined"
    assert classify("a.jpg", mime="audio/mpeg")["admission_status"] == "quarantined"
    assert classify("data/labels/a.json")["usage_role"] == "annotation"


def test_alias_cycles_and_priority_conflicts() -> None:
    """Verify alias cycles and priority conflicts."""
    contract = get_contract()
    contract.root["formatAliases"] = [{"alias": "a", "target": "b"}, {"alias": "b", "target": "a"}]
    with pytest.raises(ValueError, match="cycle"):
        validate_contract(contract)
    contract = get_contract()
    contract["roleRules"].append(contract["roleRules"][0])
    with pytest.raises(ValueError, match="priority"):
        validate_contract(contract)


def test_runtime_role_ambiguity_and_precedence() -> None:
    """Verify runtime role ambiguity and precedence."""
    conflict = classify("annotations/camera_config/sample.json")
    assert conflict["resolutionStatus"] == "ambiguous"
    assert conflict["conflicts"] == ["annotation", "metadata"]
    resolved = classify("annotations/camera_config/sample.json", standardRole="payload")
    assert resolved["usage_role"] == "payload"
    assert resolved["admission_status"] == "accepted"
    assert classify("sample.json", manifestRole=["metadata"])["usage_role"] == "metadata"
