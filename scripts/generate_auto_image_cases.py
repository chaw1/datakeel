# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate six independent, scripted image routing fixtures without downloading assets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from PIL import Image, ImageDraw, ImageFont

from datakeel.core.kg_contracts import ExtractedEntity, ExtractedRelation
from datakeel.core.kg_eval_models import GoldEntity, GoldRelation
from datakeel.core.kg_image_eval import KGImageCase, KGImageSuite
from datakeel.core.kg_models import RawExtraction, Recording, RecordingRecord
from datakeel.core.transcription_models import OCRLine, TranscriptionRecord, TranscriptionRecording

ROOT = Path(__file__).resolve().parents[1] / "contracts" / "kg"
SIZE = (900, 420)
FONT = ImageFont.load_default(size=26)


@dataclass(frozen=True)
class Fixture:
    """Keep authored semantic facts separate from the rendering and observed scripts."""

    name: str
    kind: Literal["text", "connector", "strike", "grey"]
    fact: tuple[str, str, str]
    types: tuple[str, str]
    text: str
    cancelled: tuple[str, str, str] | None = None


FIXTURES = (
    Fixture(
        "text-staff",
        "text",
        ("Ari", "works_for", "Cedar Labs"),
        ("person", "organization"),
        "Ari works for Cedar Labs.",
    ),
    Fixture(
        "text-location",
        "text",
        ("Maple Team", "located_in", "Oslo"),
        ("organization", "location"),
        "Maple Team is located in Oslo.",
    ),
    Fixture(
        "text-lineage",
        "text",
        ("daily_sales", "derived_from", "raw_sales"),
        ("dataset", "dataset"),
        "daily_sales is derived from raw_sales.",
    ),
    Fixture(
        "connector",
        "connector",
        ("Field Ops", "part_of", "Operations"),
        ("organization", "organization"),
        "Field Ops is part of Operations.",
    ),
    Fixture(
        "strike",
        "strike",
        ("Rina", "owns", "current_orders"),
        ("person", "dataset"),
        "Rina owns current_orders.",
        ("Milo", "owns", "legacy_orders"),
    ),
    Fixture(
        "grey",
        "grey",
        ("Nora", "owns", "active_inventory"),
        ("person", "dataset"),
        "Nora owns active_inventory.",
        ("Owen", "owns", "retired_inventory"),
    ),
)


def _line(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, color: str = "black") -> OCRLine:
    draw.text((x, y), text, fill=color, font=FONT)
    return OCRLine(text=text, bbox=draw.textbbox((x, y), text, font=FONT), confidence=0.99)


def _render(fixture: Fixture) -> tuple[Image.Image, tuple[OCRLine, ...], str]:
    image = Image.new("RGB", SIZE, "white")
    draw = ImageDraw.Draw(image)
    lines = [_line(draw, "Current organisation and data register", 50, 30)]
    if fixture.kind == "connector":
        lines.extend((_line(draw, "Operations", 330, 110), _line(draw, "Field Ops", 345, 310)))
        draw.rounded_rectangle((310, 95, 525, 155), outline="black", width=2, radius=7)
        draw.rounded_rectangle((315, 295, 520, 355), outline="black", width=2, radius=7)
        draw.line((417, 294, 417, 155), fill="black", width=4)
        draw.polygon(((417, 155), (406, 173), (428, 173)), fill="black")
        return image, tuple(lines), fixture.text
    lines.append(_line(draw, fixture.text, 50, 110))
    if fixture.cancelled is not None:
        head, _, tail = fixture.cancelled
        cancelled = f"{head} owns {tail}."
        if fixture.kind == "grey":
            draw.rectangle((35, 190, 860, 255), fill="#d0d0d0")
        line = _line(draw, cancelled, 50, 205, "#858585" if fixture.kind == "grey" else "black")
        lines.append(line)
        if fixture.kind == "strike":
            x1, y1, x2, y2 = line.bbox
            draw.line((x1, (y1 + y2) / 2, x2, (y1 + y2) / 2), fill="black", width=3)
        lines.append(_line(draw, "Struck or shaded rows are cancelled.", 50, 320))
        return image, tuple(lines), f"{fixture.text}\nCancelled: {cancelled}"
    lines.extend(
        (
            _line(draw, "This register lists current facts only.", 50, 175),
            _line(draw, "Reviewed and approved for this example.", 50, 240),
        )
    )
    return image, tuple(lines), "\n".join(line.text for line in lines)


def _output(fixture: Fixture, text: str, *, flattened: bool) -> RawExtraction:
    triples = [fixture.fact]
    if flattened and fixture.kind == "connector":
        triples = []
    if flattened and fixture.cancelled is not None:
        triples.append(fixture.cancelled)
    names = {fixture.fact[0]: fixture.types[0], fixture.fact[2]: fixture.types[1]}
    if fixture.cancelled:
        names.update(
            {fixture.cancelled[0]: fixture.types[0], fixture.cancelled[2]: fixture.types[1]}
        )
    return RawExtraction(
        entities=tuple(ExtractedEntity(name=name, type=kind) for name, kind in names.items()),
        relations=tuple(
            ExtractedRelation(head=h, relation=r, tail=t, evidence=text) for h, r, t in triples
        ),
    )


def _case(fixture: Fixture, content: bytes, text: str) -> KGImageCase:
    head, relation, tail = fixture.fact
    entities = [
        GoldEntity(name=head, type=fixture.types[0]),
        GoldEntity(name=tail, type=fixture.types[1]),
    ]
    traps: tuple[GoldRelation, ...] = ()
    if fixture.cancelled:
        first, label, last = fixture.cancelled
        entities.extend(
            (
                GoldEntity(name=first, type=fixture.types[0]),
                GoldEntity(name=last, type=fixture.types[1]),
            )
        )
        traps = (GoldRelation(head=first, relation=label, tail=last),)
    return KGImageCase(
        id=fixture.name,
        lang="en",
        group="A_clean" if fixture.kind == "text" else "B",
        image=f"images/{fixture.name}.png",
        image_hash=hashlib.sha256(content).hexdigest(),
        width=SIZE[0],
        height=SIZE[1],
        text=text,
        entities=tuple(entities),
        relations=(GoldRelation(head=head, relation=relation, tail=tail),),
        traps=traps,
        expected_route="ocr" if fixture.kind == "text" else "vlm",
    )


def _dump_fixture(model: KGImageSuite | TranscriptionRecording | Recording) -> str:
    # Keep the established pixel-only recordings reproducible without new default metadata.
    return yaml.safe_dump(
        model.model_dump(
            mode="json",
            exclude_none=True,
            exclude={
                "coordinate_space": True,
                "records": {"__all__": {"coordinate_space", "ignored_field_count"}},
            }
            if isinstance(model, TranscriptionRecording)
            else None,
        ),
        allow_unicode=True,
        sort_keys=False,
    )


def main() -> None:
    """Write portable labels and explicitly synthetic replay observations deterministically."""
    directory = ROOT / "eval" / "image-auto"
    (directory / "images").mkdir(parents=True, exist_ok=True)
    cases: list[KGImageCase] = []
    transcripts: list[TranscriptionRecord] = []
    outputs: dict[str, RecordingRecord] = {}
    for fixture in FIXTURES:
        image, lines, visual = _render(fixture)
        target = directory / "images" / f"{fixture.name}.png"
        image.save(target)
        content = target.read_bytes()
        cases.append(_case(fixture, content, visual))
        transcripts.append(
            TranscriptionRecord(
                image_hash=cases[-1].image_hash or "",
                text=visual,
                lines=lines,
                width=SIZE[0],
                height=SIZE[1],
                backend="vlm",
                model="scripted-auto-fixture",
                mode="vlm",
            )
        )
        for flattened, text in ((True, "\n".join(line.text for line in lines)), (False, visual)):
            digest = hashlib.sha256(text.encode()).hexdigest()
            outputs.setdefault(
                digest,
                RecordingRecord(
                    text_hash=digest,
                    output=_output(fixture, text, flattened=flattened),
                ),
            )
    archive = TranscriptionRecording(
        model="scripted-auto-fixture",
        recorded_at="2026-10-26",
        prompt_version="image-transcription-v1",
        source="Scripted observations for generated images; no real model was run.",
        records=tuple(transcripts),
    )
    recording = Recording(
        model="scripted-auto-fixture",
        recorded_at="2026-10-26",
        prompt_version="image-kg-v1",
        source="Scripted extraction illustrates flattened OCR and retained visual structure.",
        records=tuple(outputs.values()),
    )
    for path, model in (
        (directory / "cases.yaml", KGImageSuite(id="generated-auto-routing", cases=tuple(cases))),
        (ROOT / "recordings" / "auto-transcription.yaml", archive),
        (ROOT / "recordings" / "auto-extraction.yaml", recording),
    ):
        path.write_text(_dump_fixture(model))


if __name__ == "__main__":
    main()
