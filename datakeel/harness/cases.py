# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Load explicit golden contracts and seed only generated local fixtures."""

from pathlib import Path
from typing import Literal

import yaml
from PIL import Image

from datakeel.core.errors import ValidationError
from datakeel.core.harness_eval import CaseFixture, GoldenCase
from datakeel.harness.asset_cases import seed_asset_case
from datakeel.harness.enterprise_cases import seed_enterprise_case
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.harness.enterprise_reviews import review_enterprise_kg
from datakeel.harness.evidence_cases import seed_evidence_case
from datakeel.harness.image_kg_cases import seed_image_kg_case
from datakeel.harness.injection_cases import seed_injection_case
from datakeel.harness.kg_cases import seed_kg_case
from datakeel.harness.resources import contract_path
from datakeel.harness.standard_cases import seed_standard_case
from datakeel.storage.database import Database
from datakeel.storage.dataset_service import import_paths, list_files

GOLDEN_PATH = contract_path("golden")


def load_cases(directory: Path | None = None) -> list[GoldenCase]:
    """Read each YAML as a validated immutable scenario with a unique identifier."""
    paths = sorted((directory or GOLDEN_PATH).glob("*.yaml"))
    if not paths:
        msg = "No golden YAML cases found"
        raise ValidationError(msg)
    cases = [GoldenCase.model_validate(yaml.safe_load(path.read_text())) for path in paths]
    if len({case.id for case in cases}) != len(cases):
        msg = "Golden case identifiers must be unique"
        raise ValidationError(msg)
    return cases


def seed_case(
    db: Database,
    directory: Path,
    kind: Literal[
        "legacy",
        "evidence",
        "enterprise",
        "injection",
        "kg",
        "enterprise_kg",
        "image_kg",
        "asset_access",
        "standards",
    ] = "legacy",
    *,
    reviewed: bool = False,
) -> CaseFixture:
    """Import an empty text, healthy text, and tiny image for actual tool effects."""
    if kind == "enterprise_kg":
        fixture = seed_enterprise_kg(db, directory)
        if reviewed:
            review_enterprise_kg(db, fixture)
        return fixture
    if kind in {"kg", "image_kg", "standards"}:
        return {
            "kg": seed_kg_case,
            "image_kg": seed_image_kg_case,
            "standards": seed_standard_case,
        }[kind](db, directory)
    if kind in {"enterprise", "asset_access"}:
        return {"enterprise": seed_enterprise_case, "asset_access": seed_asset_case}[kind](
            db, directory
        )
    if kind == "injection":
        return seed_injection_case(db, directory)
    if kind == "evidence":
        return seed_evidence_case(db, directory)
    empty, healthy, picture = [
        directory / name for name in ("empty.txt", "healthy.txt", "image.png")
    ]
    empty.write_text("")
    healthy.write_text("Generated observation for deterministic evaluation.")
    Image.new("RGB", (8, 8), color="blue").save(picture)
    dataset = import_paths(db, "Generated golden fixture", [empty, healthy, picture])
    file = next(item for item in list_files(db, dataset.id) if item.filename == "empty.txt")
    return CaseFixture(dataset_id=dataset.id, file_id=file.id)


def bind_case(case: GoldenCase, fixture: CaseFixture) -> GoldenCase:
    """Substitute generated identifiers without changing the declared assertions."""
    raw = case.model_dump_json()
    for name, value in fixture.model_dump().items():
        raw = raw.replace("{{" + name + "}}", value)
    bound = GoldenCase.model_validate_json(raw)
    return bound.model_copy(
        update={
            "config": bound.config.model_copy(
                update={
                    "dataset_id": fixture.dataset_id,
                    "model": "fake-script"
                    if bound.config.provider == "fake"
                    else bound.config.model,
                }
            )
        }
    )
