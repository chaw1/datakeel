# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Direct pair evidence and independent clean controls for all four checked signals."""

from datakeel.core.models import FileItem, utcnow
from datakeel.core.training_models import SplitRatios, SplitRequest, SplitSet, TrainingSample
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


def test_three_signals_emit_pairs_with_distance_and_partitions() -> None:
    """Every planted cross-set signal is recalled with zero unrelated direct pairs."""
    samples = (
        _sample("exact-left", "train"),
        _sample("exact-right", "val"),
        _sample("image-left", "train", image_hash=0x1234567890ABCDEF),
        _sample("image-right", "test", image_hash=0x1234567890ABCDEE),
        _sample("text-left", "train", text_hash=123),
        _sample("text-right", "val", text_hash=123),
        _sample("group-left", "val", group="batch-7"),
        _sample("group-right", "test", group="batch-7"),
        _sample(
            "clean",
            "test",
            image_hash=0xEDCBA9876F543210,
            text_hash=456,
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
    assert report.checked_signals == ("exact", "image", "text", "group")
    assert {pair.kind for pair in report.pairs} == {"exact", "image", "text", "group"}
    assert len(report.pairs) == 4
    assert all(pair.left_split != pair.right_split and pair.detail for pair in report.pairs)
    assert next(pair.distance for pair in report.pairs if pair.kind == "image") == 1
    assert samples[4].model_dump()["text_hash"] == 123
    legacy = leakage_report(
        samples, _split(samples).model_copy(update={"algorithm_version": "1.2-primary-no-text"})
    )
    assert legacy.checked_signals == ("exact", "image", "group")
    assert {pair.kind for pair in legacy.pairs} == {"exact", "image", "group"}


def test_byte_identical_text_has_one_exact_pair_without_a_second_text_pair() -> None:
    """A repeated file contributes one reported pair; missing hashes cannot imply exactness."""
    samples = (_sample("left", "train", text_hash=123), _sample("right", "test", text_hash=123))
    identical = (
        samples[0],
        samples[1].model_copy(
            update={"file": samples[1].file.model_copy(update={"sha256": "left"})}
        ),
    )
    assert [pair.kind for pair in leakage_report(identical, _split(identical)).pairs] == ["exact"]
    assert [pair.kind for pair in leakage_report(samples, _split(samples)).pairs] == ["text"]
    missing = tuple(
        sample.model_copy(update={"file": sample.file.model_copy(update={"sha256": None})})
        for sample in samples
    )
    assert [pair.kind for pair in leakage_report(missing, _split(samples)).pairs] == ["text"]


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


def test_text_threshold_is_inclusive_and_prefix_boundaries_are_lossless() -> None:
    """Hamming thresholds change direct text pairs without inferring transitive matches."""
    samples = (
        _sample("a", "train", text_hash=0),
        _sample("b", "val", text_hash=1 << 63),
        _sample("c", "test", text_hash=(1 << 63) | 255),
    )
    split = _split(samples)
    pairs = leakage_report(samples, split).pairs
    assert [(pair.left_id, pair.right_id, pair.distance) for pair in pairs] == [("a", "b", 1)]
    assert not leakage_report(
        samples, split.model_copy(update={"request": SplitRequest(name="none", text_threshold=0)})
    ).pairs
    wider = leakage_report(
        samples, split.model_copy(update={"request": SplitRequest(name="wide", text_threshold=8)})
    ).pairs
    assert [(pair.left_id, pair.right_id, pair.distance) for pair in wider] == [
        ("a", "b", 1),
        ("b", "c", 8),
    ]
    all_pairs = leakage_report(
        samples, split.model_copy(update={"request": SplitRequest(name="all", text_threshold=64)})
    ).pairs
    assert len(all_pairs) == 3


def test_generated_split_co_locates_text_duplicate_components() -> None:
    """Text edges join the same indivisible groups as content, images and explicit group keys."""
    samples = (
        _sample("a", "train", text_hash=0),
        _sample("b", "val", text_hash=1 << 63),
        _sample("c", "test", text_hash=(1 << 63) | 255),
        _sample("clean", "test", text_hash=(1 << 64) - 1),
    )
    ratios = SplitRatios(train=0.5, val=0.25, test=0.25)
    assignments = {
        member.sample_id: member.split
        for member in split_samples(
            samples, SplitRequest(name="components", ratios=ratios, text_threshold=8)
        )
    }
    assert assignments["a"] == assignments["b"] == assignments["c"]
    unguarded = {
        member.sample_id: member.split
        for member in split_samples(
            samples,
            SplitRequest(name="unguarded", ratios=ratios, avoid_leakage=False, text_threshold=8),
        )
    }
    assert len({unguarded[identity] for identity in ("a", "b", "c")}) > 1
