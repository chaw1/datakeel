# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Build deterministic paired inputs and ground truth without external data."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from itertools import repeat
from pathlib import Path
from typing import Literal

from datakeel.sample_evidence.images import (
    chain_image,
    chain_indices,
    perturb_image,
    synthetic_image,
)
from datakeel.sample_evidence.models import (
    Annotation,
    AnnotationSidecar,
    GoldSample,
    NearDuplicatePair,
    NonTransitiveChain,
    SampleGold,
    Transformation,
)

TRANSFORMATIONS: tuple[Transformation, ...] = ("crop", "resize", "noise")


def _caption(index: int, concepts: list[str], scenes: Mapping[str, str]) -> str:
    subject = " and ".join(
        "pedestrian" if name == "person" and index % 2 else name for name in concepts
    )
    setting = ", ".join(name for name, value in scenes.items() if value == "present")
    return f"Generated scene {index:04d}: {subject or 'an empty scene'}; {setting or 'a scene'}.\n"


def _sample(index: int, samples: int) -> GoldSample:
    train_count = samples * 4 // 5
    duplicate_count = samples // 20
    missing_count = samples * 3 // 100
    gap = train_count <= index < train_count + duplicate_count
    missing = train_count + duplicate_count <= index < train_count + duplicate_count + missing_count
    corrupt = index >= samples - samples // 100
    original = index - train_count if gap else index
    person = original % 3 in (0, 1) or gap or missing or original < duplicate_count
    concepts = (["person"] if person else []) + (["car"] if original % 4 in (0, 1) else [])
    categories = (
        [] if missing else [concept for concept in concepts if concept != "person" or not gap]
    )
    scenes: dict[str, Literal["present", "unknown"]] = {
        "night": "present" if original % 4 == 0 else "unknown",
        "rain": "present" if original % 5 == 0 else "unknown",
        "indoor": "present" if original % 7 == 0 else "unknown",
    }
    split = "train" if index < train_count else "val"
    sample_id = f"scene-{index:04d}"
    relative = f"{split}/{sample_id}"
    return GoldSample(
        sample_id=sample_id,
        image=f"{relative}/image.png",
        caption_path=f"{relative}/caption.txt",
        annotation_path=None if missing else f"{relative}/annotations.json",
        split=split,
        caption=_caption(index, concepts, scenes),
        concepts=concepts,
        annotation_categories=categories,
        scenes=scenes,
        label_gaps=["person"] if gap else [],
        corrupt=corrupt,
        missing_annotation=missing,
        dark_scene=original % 10 == 0 and index not in chain_indices(samples),
    )


def _write_sidecars(directory: Path, sample: GoldSample) -> None:
    (directory / sample.caption_path).write_text(sample.caption, encoding="utf-8")
    annotations = [
        Annotation(category=category, bbox=(24 + index * 72, 28, 48, 72))
        for index, category in enumerate(sample.annotation_categories)
    ]
    annotation_path = directory / sample.image.replace("image.png", "annotations.json")
    if sample.missing_annotation:
        annotation_path.unlink(missing_ok=True)
    else:
        sidecar = AnnotationSidecar(annotations=annotations)
        annotation_path.write_text(sidecar.model_dump_json(indent=2) + "\n", encoding="utf-8")


def _write_sample(directory: Path, sample: GoldSample, index: int, samples: int) -> None:
    path = directory / sample.image
    path.parent.mkdir(parents=True, exist_ok=True)
    if sample.corrupt:
        path.write_bytes(f"generated-corrupt-image-{index:04d}\n".encode())
    else:
        original = index - samples * 4 // 5 if sample.label_gaps else index
        image = synthetic_image(original, dark=sample.dark_scene)
        if index in chain_indices(samples):
            image = chain_image(chain_indices(samples).index(index))
        if sample.label_gaps:
            image = perturb_image(image, TRANSFORMATIONS[original % len(TRANSFORMATIONS)], original)
        image.save(path, format="PNG", compress_level=6)
    _write_sidecars(directory, sample)


def _chains(records: list[GoldSample], pairs: list[NearDuplicatePair]) -> list[NonTransitiveChain]:
    indices = chain_indices(len(records))
    if not indices:
        return []
    a, b, c = (records[index].image for index in indices)
    pairs.extend(
        [
            NearDuplicatePair(left=a, right=b, transformation="controlled_chain"),
            NearDuplicatePair(left=b, right=c, transformation="controlled_chain"),
        ]
    )
    return [NonTransitiveChain(a=a, b=b, c=c)]


def generate_samples(directory: Path, samples: int = 1000) -> SampleGold:
    """Generate paired samples and independent gold using stable seed 17.

    Inputs live under ``train|val/scene-NNNN`` with an image and caption; three
    percent intentionally omit annotations. Five percent are val-to-train image
    pairs whose val annotation omits the mentioned person. One percent cannot
    decode. At least 100 samples also include one controlled non-transitive
    similarity chain. Integer rounding applies to smaller sample counts.
    """
    if samples < 1:
        msg = "samples must be a positive integer"
        raise ValueError(msg)
    directory.mkdir(parents=True, exist_ok=True)
    records = [_sample(index, samples) for index in range(samples)]
    train_count = samples * 4 // 5
    pairs = [
        NearDuplicatePair(
            left=records[index].image,
            right=records[train_count + index].image,
            transformation=TRANSFORMATIONS[index % len(TRANSFORMATIONS)],
        )
        for index in range(samples // 20)
    ]
    chains = _chains(records, pairs)
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="sample") as pool:
        for _ in pool.map(
            _write_sample, repeat(directory), records, range(samples), repeat(samples)
        ):
            pass
    gold = SampleGold(
        sample_count=samples,
        train_count=train_count,
        val_count=samples - train_count,
        samples=records,
        near_duplicate_pairs=pairs,
        non_transitive_chains=chains,
    )
    (directory / "gold.json").write_text(gold.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return gold
