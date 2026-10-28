# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct pair evidence and independent clean controls for all four leakage signals."""

from datakeel.core.models import FileItem, utcnow
from datakeel.core.training_models import SplitRequest, SplitSet, TrainingSample
from datakeel.training.hashes import simhash
from datakeel.training.leakage import leakage_report
from datakeel.training.splitting import distributions, split_samples


def _sample(identity: str, split: str, **values: object) -> TrainingSample:
    return TrainingSample.model_validate(
        {
            "file": FileItem(
                id=identity,
                path="unused",
                filename=identity,
                sha256=identity,
                metadata={"split": split},
            ),
            **values,
        }
    )


def _split(samples: tuple[TrainingSample, ...]) -> SplitSet:
    request = SplitRequest(name="external", source="directory")
    members = split_samples(samples, request)
    return SplitSet(
        id="split",
        dataset_id="dataset",
        version_id="version",
        request=request,
        members=members,
        distributions=distributions(members),
        created_at=utcnow(),
    )


def test_four_signals_emit_pairs_with_distance_and_partitions() -> None:
    """Every planted cross-set signal is recalled with zero unrelated direct pairs."""
    samples = (
        _sample("exact-left", "train"),
        _sample("exact-right", "val"),
        _sample("image-left", "train", image_hash=0x1234567890ABCDEF),
        _sample("image-right", "test", image_hash=0x1234567890ABCDEE),
        _sample("text-left", "train", text_hash=simhash("A quick brown fox, jumps!")),
        _sample("text-right", "val", text_hash=simhash("a QUICK brown fox jumps")),
        _sample("group-left", "val", group="batch-7"),
        _sample("group-right", "test", group="batch-7"),
        _sample(
            "clean",
            "test",
            image_hash=0xEDCBA9876F543210,
            text_hash=simhash("quantum physics and long distant stars"),
        ),
    )
    samples = (
        samples[0],
        samples[1].model_copy(
            update={"file": samples[1].file.model_copy(update={"sha256": "exact-left"})}
        ),
        *samples[2:],
    )
    report = leakage_report(samples, _split(samples))
    assert {pair.kind for pair in report.pairs} == {"exact", "image", "text", "group"}
    assert len(report.pairs) == 4
    assert all(pair.left_split != pair.right_split and pair.detail for pair in report.pairs)
    assert next(pair.distance for pair in report.pairs if pair.kind == "image") == 1


def test_report_excludes_within_set_and_does_not_invent_transitive_pairs() -> None:
    """Exact comparison finds prefix-boundary neighbors without claiming transitive matches."""
    samples = (
        _sample("a", "train", image_hash=0),
        _sample("b", "val", image_hash=1 << 63),
        _sample("c", "val", image_hash=(1 << 63) | 255),
    )
    split = _split(samples).model_copy(
        update={"request": SplitRequest(name="edges", image_threshold=8)}
    )
    pairs = leakage_report(samples, split).pairs
    assert {(pair.left_id, pair.right_id) for pair in pairs} == {("a", "b")}
