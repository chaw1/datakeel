# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Drafting a label set is a signed action; people edit the draft and publish it."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.actions import service
from datakeel.core.errors import BudgetError, ValidationError
from datakeel.core.intent_models import PageContext
from datakeel.core.label_guidelines import LabelGuideline, LabelGuidelines
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.core.production_catalog_models import LabelSet
from datakeel.core.production_reads import ProductionObjectQuery
from datakeel.core.standard_models import CodeEntry, CodeList, FieldStandard, StandardsContract
from datakeel.label_drafts.model import model_draft
from datakeel.label_drafts.models import CategorySource, DraftInputs, SampleSource
from datakeel.storage.annotation_rows import AnnotationBatchRow
from datakeel.storage.dataset_service import list_files, list_versions
from datakeel.storage.production_objects import production_objects
from tests.intents.support import images, plan, run_to_end
from tests.production_team_support import ServiceRunner
from tests.standards_support import approved_change

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database

DRAFT = "按这批图起草一份车辆标签和标注指南"


def vehicle_standards(db: Database) -> None:
    """A vehicle type code list and an occlusion flag, approved like any standards import."""
    contract = StandardsContract(
        standards=(
            FieldStandard(
                code="vehicle_type",
                name_zh="车辆类型",
                name_en="Vehicle type",
                description="Kind of road vehicle",
                data_type="string",
                code_list="vehicle_types",
                status="active",
            ),
            FieldStandard(
                code="vehicle_occluded",
                name_zh="车辆遮挡",
                name_en="Vehicle occluded",
                description="Whether part of the vehicle is hidden",
                data_type="string",
                code_list="yes_no",
                status="active",
            ),
        ),
        code_lists=(
            CodeList(
                code="vehicle_types",
                name="Vehicle types",
                status="active",
                entries=(
                    CodeEntry(value="car", label_zh="轿车", label_en="Car"),
                    CodeEntry(value="truck", label_zh="货车", label_en="Truck"),
                    CodeEntry(value="bus", label_zh="公交车", label_en="Bus"),
                ),
            ),
            CodeList(
                code="yes_no",
                name="Yes or no",
                status="active",
                entries=(
                    CodeEntry(value="yes", label_zh="是", label_en="Yes"),
                    CodeEntry(value="no", label_zh="否", label_en="No"),
                ),
            ),
        ),
    )
    run = approved_change(
        db, "import_standards", JsonDocument({"contract": contract.model_dump(mode="json")})
    )
    assert run.status == "SUCCEEDED", run.error


def label_sets(db: Database) -> list[LabelSet]:
    """Every stored label set version."""
    found = production_objects(db, ProductionObjectQuery(kind="label_set"))
    return [LabelSet.model_validate(item.properties) for item in found]


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATAKEEL_DRAFT_TEXT_API_KEY", "DATAKEEL_DRAFT_VISION_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_draft_sentence_plans_one_signed_step_and_writes_nothing(
    db: Database, tmp_path: Path
) -> None:
    """The draft is a controlled action that waits for a signature before reading anything."""
    vehicle_standards(db)
    dataset = images(db, tmp_path / "images")
    result = plan(db, DRAFT, PageContext(dataset_id=dataset.id))
    assert result.kind == "plan", result.text
    assert result.chain is not None
    (step,) = result.chain.steps
    assert step.action == "draft_label_set"
    assert sorted(step.params["standard_codes"]) == ["vehicle_occluded", "vehicle_type"]  # type: ignore[arg-type]
    assert len(step.params["sample_ids"]) == 4  # type: ignore[arg-type]
    assert step.params["profile"] == "offline"
    assert step.estimate.requires_approval
    assert label_sets(db) == []
    first = run_to_end(db, result.chain).model_copy()
    assert first.status == "succeeded"


def test_offline_draft_covers_the_standard_and_records_its_sources(
    db: Database, tmp_path: Path
) -> None:
    """Every code-list entry becomes a label; the second standard becomes an attribute."""
    vehicle_standards(db)
    dataset = images(db, tmp_path / "images")
    chain = plan(db, DRAFT, PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    assert run_to_end(db, chain).status == "succeeded"
    (drafted,) = label_sets(db)
    assert not drafted.published
    names = {label.name_zh for label in drafted.labels}
    assert {"轿车", "货车", "公交车"} <= names
    root = next(label for label in drafted.labels if label.parent_id is None)
    assert [field.key for field in root.fields] == ["vehicle_occluded"]
    assert {label.name_en for label in drafted.labels} >= {"Car", "Truck", "Bus"}
    assert drafted.guidelines is not None
    assert drafted.draft_source is not None
    assert set(drafted.draft_source.standard_codes) == {"vehicle_type", "vehicle_occluded"}
    assert set(drafted.draft_source.sample_ids) == {item.id for item in list_files(db, dataset.id)}
    assert drafted.draft_source.model == "offline-rules"


def test_existing_annotations_add_categories_and_cite_real_samples(
    db: Database, tmp_path: Path
) -> None:
    """Annotated samples contribute categories and become positive examples by their IDs."""
    dataset = images(db, tmp_path / "images")
    files = list_files(db, dataset.id)
    version = list_versions(db, dataset.id)[0]
    batch = {
        "annotations": [
            {"sample_id": files[0].id, "annotator_id": "ann", "labels": ["红灯"]},
            {"sample_id": files[1].id, "annotator_id": "ann", "labels": ["绿灯"]},
        ]
    }
    with db.session() as session:
        session.add(
            AnnotationBatchRow(
                id=new_id(),
                dataset_id=dataset.id,
                version_id=version.id,
                idempotency_key="generated",
                request_digest="generated",
                batch=batch,
                report={},
                created_at=utcnow().timestamp(),
            )
        )
        session.commit()
    chain = plan(db, "参考已有标注起草信号灯标签", PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    assert chain.steps[0].params["annotation_dataset_ids"] == [dataset.id]
    assert run_to_end(db, chain).status == "succeeded"
    (drafted,) = label_sets(db)
    assert {"红灯", "绿灯"} <= {label.name for label in drafted.labels}
    assert drafted.guidelines is not None
    cited = {item.sample_id for rule in drafted.guidelines.rules for item in rule.examples}
    assert cited == {files[0].id, files[1].id}


def test_people_edit_guidelines_and_publish_keeping_the_provenance(
    db: Database, tmp_path: Path
) -> None:
    """An edit replaces the text through create_label_set; publishing uses the usual action."""
    vehicle_standards(db)
    dataset = images(db, tmp_path / "images")
    chain = plan(db, DRAFT, PageContext(dataset_id=dataset.id)).chain
    assert chain is not None
    run_to_end(db, chain)
    (drafted,) = label_sets(db)
    runner = ServiceRunner(db)
    edited = LabelGuidelines(
        overview_zh="只标完整可见的车辆。",
        overview_en="Only fully visible vehicles.",
        rules=(LabelGuideline(label_id=drafted.labels[1].id, text_zh="改过", text_en="Edited"),),
    )
    runner(
        "create_label_set",
        {
            "operation": "update",
            "label_set_id": drafted.id,
            "version": drafted.version,
            "name": drafted.name,
            "labels": [label.model_dump(mode="json") for label in drafted.labels],
            "guidelines": edited.model_dump(mode="json"),
        },
    )
    runner("publish_label_set", {"label_set_id": drafted.id, "version": drafted.version})
    (published,) = label_sets(db)
    assert published.published
    assert published.guidelines == edited
    assert published.draft_source == drafted.draft_source


def test_guideline_rules_must_name_labels_of_the_version(db: Database) -> None:
    """A rule for a label that does not exist is rejected when the edit is prepared."""
    rules = LabelGuidelines(rules=(LabelGuideline(label_id="ghost", text_zh="x", text_en="x"),))
    with pytest.raises(ValidationError, match="Guideline rules"):
        ServiceRunner(db)(
            "create_label_set",
            {
                "name": "Signals",
                "labels": [{"id": "red", "name": "Red"}],
                "guidelines": rules.model_dump(mode="json"),
            },
        )
    assert service.list_runs(db) == [] or all(
        run.status != "SUCCEEDED" for run in service.list_runs(db)
    )


RECORDED = {
    "choices": [
        {
            "message": {
                "content": json.dumps(
                    {
                        "labels": [{"id": "car", "name_zh": "轿车", "name_en": "Car"}],
                        "overview_zh": "车辆框",
                        "overview_en": "Vehicle boxes",
                        "rules": [
                            {
                                "label_id": "car",
                                "text_zh": "框住整车",
                                "text_en": "Box the whole car",
                                "positive": [{"sample_id": "s-1", "note": "清晰"}],
                                "negative": [{"sample_id": "invented", "note": "不存在"}],
                            }
                        ],
                    }
                )
            }
        }
    ],
    "usage": {"prompt_tokens": 1200, "completion_tokens": 300},
}


def _inputs() -> DraftInputs:
    return DraftInputs(
        name="车辆",
        topic="车辆",
        categories=(
            CategorySource(key="car", name_zh="轿车", name_en="Car"),
            CategorySource(key="bus", name_zh="公交车", name_en="Bus"),
        ),
        samples=(
            SampleSource(id="s-1", filename="a.png", image_data_url="data:image/jpeg;base64,AA"),
        ),
    )


def test_recorded_model_draft_keeps_every_category_and_drops_invented_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A model that forgets a category or cites an unknown sample cannot change coverage."""
    monkeypatch.setenv("DATAKEEL_DRAFT_VISION_API_KEY", "test-only")
    sent: list[dict[str, object]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=RECORDED)

    with httpx.Client(transport=httpx.MockTransport(reply)) as client:
        outcome = model_draft(_inputs(), "cloud-vision", 0.05, client)
    assert {label.id for label in outcome.labels} == {"car", "bus"}
    (rule,) = outcome.guidelines.rules
    assert [item.sample_id for item in rule.examples] == ["s-1"]
    assert outcome.dropped_examples == 1
    assert outcome.input_tokens == 1200
    assert outcome.cost_usd > 0
    content = sent[0]["messages"]
    assert "image_url" in json.dumps(content)


def test_model_draft_refuses_a_budget_below_its_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    """The approved budget caps the request before anything is sent."""
    monkeypatch.setenv("DATAKEEL_DRAFT_VISION_API_KEY", "test-only")

    def reply(request: httpx.Request) -> httpx.Response:
        raise AssertionError(request.url)

    with (
        httpx.Client(transport=httpx.MockTransport(reply)) as client,
        pytest.raises(BudgetError),
    ):
        model_draft(_inputs(), "cloud-vision", 0.000001, client)
