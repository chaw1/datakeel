# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate fictional harbor observations and three independent annotation panels."""

from pathlib import Path

from PIL import Image, ImageDraw

from datakeel.core.annotation_models import (
    AnnotationBatch,
    AnnotationBox,
    AnnotationRecord,
    AnnotationSpan,
    NearDuplicatePair,
)
from datakeel.core.models import BoundaryModel

ANNOTATORS = ("reviewer-amber", "reviewer-cobalt", "reviewer-jade")
SAMPLE_COUNT = 24
_DUPLICATE_INDEX = 7
_CONFLICT_INDEX = 3
_SPAN_ERROR_INDEX = 2
_REGRESSION_INDEX = 12
_BOUNDARY_INDEX = 9
_MISSED_BOX_INDEX = 10


class AnnotationQASamples(BoundaryModel):
    """Keep generated source files beside reproducible initial and repaired panels."""

    paths: tuple[Path, ...]
    initial: AnnotationBatch
    reworked: AnnotationBatch


def _record(index: int, annotator: str) -> AnnotationRecord:
    text = f"Beacon Aster guides ferry {index:02d}."
    return AnnotationRecord(
        sample_id=f"harbor-{index:02d}.png",
        annotator_id=annotator,
        labels=("clear" if index % 2 == 0 else "restricted",),
        boxes=(AnnotationBox(category="beacon", x1=20, y1=20, x2=40, y2=40),),
        spans=(AnnotationSpan(category="beacon_name", start=7, end=12),),
        text_length=len(text),
        image_width=128,
        image_height=96,
    )


def _beacon(x1: float, y1: float, x2: float, y2: float) -> tuple[AnnotationBox, ...]:
    return (AnnotationBox(category="beacon", x1=x1, y1=y1, x2=x2, y2=y2),)


def _name(start: int, end: int) -> tuple[AnnotationSpan, ...]:
    return (AnnotationSpan(category="beacon_name", start=start, end=end),)


_PLANTED: dict[int, dict[str, object]] = {
    0: {"labels": ("restricted",)},
    1: {"boxes": _beacon(40, 20, 20, 40)},
    _SPAN_ERROR_INDEX: {"spans": _name(7, 200)},
    _CONFLICT_INDEX: {"labels": ("clear", "restricted")},
    4: {"boxes": _beacon(0, 0, 127, 95)},
    5: {"boxes": _beacon(20, 20, 120, 21)},
    _BOUNDARY_INDEX: {"spans": _name(7, 14)},
    _MISSED_BOX_INDEX: {"boxes": ()},
}


def _plant(record: AnnotationRecord, index: int) -> AnnotationRecord:
    """Only the third reviewer makes the planted mistakes, so the panel has a majority."""
    if record.annotator_id != ANNOTATORS[2] or index not in _PLANTED:
        return record
    return record.model_copy(update=_PLANTED[index])


def _batch(records: tuple[AnnotationRecord, ...]) -> AnnotationBatch:
    return AnnotationBatch(
        annotations=records,
        near_duplicates=(
            NearDuplicatePair(sample_id="harbor-06.png", other_sample_id="harbor-07.png"),
        ),
        exclusive_label_groups=(("clear", "restricted"),),
    )


def generate_annotation_qa_samples(directory: Path) -> AnnotationQASamples:
    """Write 24 fictional images, embedded notes and panels with ten kinds of suspicion.

    Span coordinates refer to the generated note rendered in the image. The
    reworked panel fixes the planted issues and introduces one new invalid span,
    making both improvement and regression visible without a model or network.
    """
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    initial: list[AnnotationRecord] = []
    reworked: list[AnnotationRecord] = []
    for index in range(SAMPLE_COUNT):
        scene = 6 if index == _DUPLICATE_INDEX else index
        path = directory / f"harbor-{index:02d}.png"
        image = Image.new("RGB", (128, 96), color=(30, 65, 90))
        drawing = ImageDraw.Draw(image)
        drawing.rectangle((20, 20, 40, 40), fill=(245, 190, 60))
        drawing.text((3, 60), "Beacon Aster", fill="white")
        drawing.text((3, 75), f"guides ferry {scene:02d}.", fill="white")
        image.save(path)
        paths.append(path)
        for annotator in ANNOTATORS:
            record = _record(index, annotator)
            initial.append(_plant(record, index))
            repaired = (
                record.model_copy(update={"labels": ("clear",)})
                if index == _DUPLICATE_INDEX
                else record
            )
            if index == _REGRESSION_INDEX and annotator == ANNOTATORS[2]:
                repaired = repaired.model_copy(
                    update={"spans": (AnnotationSpan(category="beacon_name", start=-1, end=12),)}
                )
            reworked.append(repaired)
    samples = AnnotationQASamples(
        paths=tuple(paths), initial=_batch(tuple(initial)), reworked=_batch(tuple(reworked))
    )
    for name, panel in (("initial", samples.initial), ("reworked", samples.reworked)):
        (directory / f"{name}.json").write_text(panel.model_dump_json(indent=2) + "\n")
    return samples
