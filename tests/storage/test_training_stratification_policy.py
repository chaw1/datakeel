# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Default identity and immutable-name compatibility require no database connections."""

from copy import deepcopy
from typing import cast
from unittest.mock import MagicMock, patch

import pytest

from datakeel.core.errors import ConflictError
from datakeel.core.models import FileItem
from datakeel.core.training_models import SplitRequest, SplitSet, TrainingSample
from datakeel.storage.database import Database
from datakeel.storage.training_rows import TrainingSplitRow
from datakeel.storage.training_store import create_split, get_split, preview_split


def _samples() -> tuple[TrainingSample, ...]:
    return tuple(
        TrainingSample(
            file=FileItem(
                id=str(index), path="unavailable", filename=f"{index}.txt", sha256=f"hash-{index}"
            ),
            labels=(f"class-{index % 2}",),
        )
        for index in range(20)
    )


def _preview(request: SplitRequest, samples: tuple[TrainingSample, ...]) -> SplitSet:
    database = cast("Database", MagicMock(spec=Database))
    with patch("datakeel.storage.training_store.read_training_samples", return_value=samples):
        return preview_split(database, "dataset", "version", request)


def test_default_all_preserves_the_previous_split_identity() -> None:
    """The published default-policy digest from before source selection remains identical."""
    request = SplitRequest(name="identity", seed=17, avoid_leakage=False)
    split = _preview(request, _samples())
    assert split.id == "4774aac3bf9b01f15b3dd2689a042455d4395ab42dd08515713fca007e394db0"
    assert split.request.stratification_source == "all"
    assert split.model_dump(mode="json")["request"]["stratification_source"] == "all"


def test_nondefault_annotation_source_is_frozen_in_identity_even_with_equal_assignments() -> None:
    """Different selected kinds remain different policies when this dataset lacks annotations."""
    samples = tuple(sample.model_copy(update={"labels": ()}) for sample in _samples())
    baseline = _preview(SplitRequest(name="policy"), samples)
    identities = {baseline.id}
    for source in ("classification", "detection", "spans"):
        split = _preview(SplitRequest(name="policy", stratification_source=source), samples)
        assert split.members == baseline.members
        assert split.request.stratification_source == source
        identities.add(split.id)
    assert len(identities) == 4


def test_old_snapshot_missing_source_reuses_its_name_and_refuses_a_changed_policy() -> None:
    """Typed defaults retain old retries and payload bytes without materializing source files."""
    request = SplitRequest(name="legacy", seed=17)
    original = _preview(request, _samples()).model_dump(mode="json")
    original["request"].pop("stratification_source")
    original["id"] = "old-snapshot"
    previous_payload = deepcopy(original)
    row = TrainingSplitRow(
        id="old-snapshot",
        dataset_id="dataset",
        version_id="version",
        name="legacy",
        created_at=0,
        payload=original,
        samples=[],
    )
    database_mock = MagicMock(spec=Database)
    session = database_mock.session.return_value.__enter__.return_value
    session.scalar.return_value = row
    session.get.return_value = row
    database = cast("Database", database_mock)
    with (
        patch("datakeel.storage.training_store.require_version"),
        patch("datakeel.storage.training_store.authorize_training"),
        patch("datakeel.storage.training_store.read_training_samples") as materialize,
    ):
        restored = create_split(database, "dataset", "version", request)
        assert restored.id == "old-snapshot"
        assert restored.request.stratification_source == "all"
        assert get_split(database, "dataset", restored.id) == restored
        for source in ("classification", "detection", "spans"):
            with pytest.raises(ConflictError, match="immutable policy"):
                create_split(
                    database,
                    "dataset",
                    "version",
                    request.model_copy(update={"stratification_source": source}),
                )
        materialize.assert_not_called()
    session.add.assert_not_called()
    session.commit.assert_not_called()
    assert row.payload == previous_payload
