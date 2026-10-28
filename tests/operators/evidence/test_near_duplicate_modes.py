# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The operator keeps canonical evidence stable when switching matching implementations."""

from pathlib import Path
from typing import Literal

import pytest
from pydantic import JsonValue

from datakeel.core.models import AssetRef, FileItem
from datakeel.operators import REGISTRY
from datakeel.operators.evidence import near_duplicate
from datakeel.operators.evidence.contracts import NearDuplicateContract, read_near_duplicate
from datakeel.operators.evidence.near_duplicate import duplicate_pairs
from tests.operators.evidence.helpers import drafts, local_file


def _files(directory: Path) -> list[FileItem]:
    output: list[FileItem] = []
    for identifier, value in (("z", 1 << 63), ("c", 7), ("a", 0), ("b", 1)):
        path = directory / f"{identifier}.png"
        path.write_bytes(f"generated source {identifier}".encode())
        file = local_file(path, identifier, "image")
        output.append(
            file.model_copy(
                update={
                    "metadata": {
                        "image_phash": f"{value:016x}",
                        "evidence_subject": AssetRef(
                            asset_type="file", asset_id=identifier, version="source-v1"
                        ).model_dump(mode="json"),
                    }
                }
            )
        )
    return output


def _factual_metadata(files: list[FileItem]) -> list[dict[str, JsonValue]]:
    return [
        {
            key: value
            for key, value in file.metadata.items()
            if key not in {"near_duplicate_implementation", "near_duplicate_implementation_version"}
        }
        for file in files
    ]


@pytest.mark.parametrize("mode", ["prefix", "exact"])
def test_operator_evidence_is_equal_for_off_auto_and_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    """Switch native backends without changing direct pairs, distances, anchors, or order."""
    files = _files(tmp_path)
    metadata: list[list[dict[str, JsonValue]]] = []
    for selection, implementation in (("off", "python"), ("auto", "rust"), ("required", "rust")):
        monkeypatch.setenv("DATAKEEL_ACCEL", selection)
        result = REGISTRY["evidence.near_duplicate"].run(files, tmp_path, {"mode": mode})
        assert result.quality["implementation"] == implementation
        assert result.quality["implementation_version"]
        assert result.quality["match_mode"] == mode
        assert all(
            file.metadata["near_duplicate_implementation"] == implementation
            and file.metadata["near_duplicate_implementation_version"]
            for file in result.files
        )
        metadata.append(_factual_metadata(result.files))
    assert metadata[0] == metadata[1] == metadata[2]
    observed = [draft for file in result.files for draft in drafts(file)]
    assert len(observed) == (3 if mode == "prefix" else 6)


@pytest.mark.parametrize("mode", ["prefix", "exact"])
def test_pair_order_uses_canonical_identity_across_input_permutations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mode: Literal["prefix", "exact"]
) -> None:
    """The same assets always produce the same sorted orientation and pair sequence."""
    monkeypatch.setenv("DATAKEEL_ACCEL", "off")
    files = _files(tmp_path)
    expected = [
        (left.id, right.id, distance) for left, right, distance in duplicate_pairs(files, mode)
    ]
    actual = [
        (left.id, right.id, distance)
        for left, right, distance in duplicate_pairs(list(reversed(files)), mode)
    ]
    assert actual == expected == sorted(expected)
    assert all(left < right for left, right, _distance in actual)


def test_contract_without_mode_keeps_prefix_and_explicit_exact_recovers_cross_bucket_pair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Legacy contracts retain default semantics, while the new mode repairs prefix misses."""
    legacy = NearDuplicateContract.model_validate(
        read_near_duplicate().model_dump(exclude={"mode"})
    )
    assert legacy.mode == "prefix"
    files = _files(tmp_path)
    monkeypatch.setattr(near_duplicate, "read_near_duplicate", lambda: legacy)
    assert len(duplicate_pairs(files)) == 3
    exact = legacy.model_copy(update={"mode": "exact"})
    monkeypatch.setattr(near_duplicate, "read_near_duplicate", lambda: exact)
    assert len(duplicate_pairs(files)) == 6
    assert len(duplicate_pairs(files, "prefix")) == 3


def test_missing_hash_is_retained_without_inventing_pair(tmp_path: Path) -> None:
    """Corrupt or unmeasured source files still carry the implementation audit metadata."""
    file = _files(tmp_path)[0]
    file = file.model_copy(update={"metadata": {**file.metadata, "image_phash": None}})
    result = REGISTRY["evidence.near_duplicate"].run([file], tmp_path)
    assert len(result.files) == 1
    assert drafts(result.files[0]) == []
    assert result.files[0].metadata["near_duplicate_implementation"] in {"python", "rust"}
