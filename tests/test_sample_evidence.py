# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated evidence cases are complete, independent, and byte reproducible."""

import hashlib
from pathlib import Path
from time import perf_counter

import numpy as np
import pytest
from PIL import Image, UnidentifiedImageError

from datakeel.sample_evidence import SampleGold, generate_samples
from datakeel.sample_evidence.models import AnnotationSidecar


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, SampleGold, float]:
    """Build the full acceptance dataset once and record its generation duration."""
    directory = tmp_path_factory.mktemp("evidence-samples")
    started = perf_counter()
    gold = generate_samples(directory)
    return directory, gold, perf_counter() - started


def _hashes(directory: Path) -> dict[str, str]:
    return {
        str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in directory.rglob("*")
        if path.is_file()
    }


def _dhash(path: Path) -> int:
    with Image.open(path) as image:
        pixels = np.asarray(image.convert("L").resize((9, 8), Image.Resampling.LANCZOS))
    return int("".join("1" if bit else "0" for bit in (pixels[:, 1:] > pixels[:, :-1]).flat), 2)


def test_generation_when_repeated_is_byte_identical_and_under_one_minute(
    generated: tuple[Path, SampleGold, float], tmp_path: Path
) -> None:
    """Verify different output roots produce the same complete byte sequence."""
    directory, gold, duration = generated
    regenerated = generate_samples(tmp_path)
    assert duration < 60
    assert gold == regenerated
    assert _hashes(directory) == _hashes(tmp_path)


def test_generation_when_default_contains_declared_case_counts(
    generated: tuple[Path, SampleGold, float],
) -> None:
    """Verify the denominator includes every synthetic case and disjoint faults."""
    _, gold, _ = generated
    assert gold.sample_count == len(gold.samples) == 1000
    assert gold.train_count == sum(sample.split == "train" for sample in gold.samples) == 800
    assert gold.val_count == 200
    assert len(gold.near_duplicate_pairs) == 52
    assert sum(bool(sample.label_gaps) for sample in gold.samples) == 50
    assert sum(sample.corrupt for sample in gold.samples) == 10
    assert sum(sample.missing_annotation for sample in gold.samples) == 30
    assert all(not sample.corrupt for sample in gold.samples if sample.missing_annotation)


def test_generation_when_sidecars_present_matches_independent_gold(
    generated: tuple[Path, SampleGold, float],
) -> None:
    """Verify images and annotation sidecars agree with expected fault locations."""
    directory, gold, _ = generated
    for sample in gold.samples:
        assert (directory / sample.caption_path).read_text(encoding="utf-8") == sample.caption
        if sample.annotation_path:
            annotations = AnnotationSidecar.model_validate_json(
                (directory / sample.annotation_path).read_bytes()
            )
            assert [
                item.category for item in annotations.annotations
            ] == sample.annotation_categories
            assert set(sample.concepts) - set(sample.annotation_categories) == set(
                sample.label_gaps
            )
        else:
            assert not (directory / sample.image).with_name("annotations.json").exists()
            assert sample.label_gaps == []
        if sample.corrupt:
            with pytest.raises(UnidentifiedImageError):
                Image.open(directory / sample.image)
        else:
            with Image.open(directory / sample.image) as image:
                assert image.size == (192, 128)
                assert (float(np.asarray(image).mean()) < 60) == sample.dark_scene


def test_generation_when_near_duplicates_injected_retains_pair_discrimination(
    generated: tuple[Path, SampleGold, float],
) -> None:
    """Verify a basic blocked dHash matcher can recover the known direct pairs."""
    directory, gold, _ = generated
    hashes = {
        sample.image: _dhash(directory / sample.image)
        for sample in gold.samples
        if not sample.corrupt
    }
    pairs = {
        (left, right)
        for left, left_hash in hashes.items()
        for right, right_hash in hashes.items()
        if left < right
        and left_hash >> 60 == right_hash >> 60
        and (left_hash ^ right_hash).bit_count() <= 8
    }
    expected = {(pair.left, pair.right) for pair in gold.near_duplicate_pairs}
    assert len(pairs & expected) / len(pairs) >= 0.9
    assert len(pairs & expected) / len(expected) >= 0.8
    assert {pair.transformation for pair in gold.near_duplicate_pairs} == {
        "crop",
        "resize",
        "noise",
        "controlled_chain",
    }
    assert all(
        (directory / pair.left).read_bytes() != (directory / pair.right).read_bytes()
        for pair in gold.near_duplicate_pairs
    )


def test_generation_when_chain_injected_has_nontransitive_measured_distances(
    generated: tuple[Path, SampleGold, float],
) -> None:
    """Verify threshold inflation links endpoints that a direct pair test excludes."""
    directory, gold, _ = generated
    chain = gold.non_transitive_chains[0]
    a, b, c = (_dhash(directory / path) for path in (chain.a, chain.b, chain.c))
    assert (a ^ b).bit_count() == chain.distance_ab == 6
    assert (b ^ c).bit_count() == chain.distance_bc == 6
    assert (a ^ c).bit_count() == chain.distance_ac == 12
    assert a >> 60 == b >> 60 == c >> 60
    assert chain.threshold < (a ^ c).bit_count() <= chain.threshold + 4


def test_generation_when_nonpositive_count_rejects_before_writing(tmp_path: Path) -> None:
    """Verify the public generator validates its sample count."""
    with pytest.raises(ValueError, match="positive"):
        generate_samples(tmp_path, 0)
    assert list(tmp_path.iterdir()) == []
