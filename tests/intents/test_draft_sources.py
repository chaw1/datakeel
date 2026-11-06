# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Drafts count sources one way, keep kinds as labels, stay complete and record spent calls."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.errors import ValidationError
from datakeel.core.intent_models import PageContext
from datakeel.core.models import JsonDocument, new_id, utcnow
from datakeel.core.standard_models import CodeEntry, CodeList, FieldStandard, StandardsContract
from datakeel.dataset_store.dataset_service import list_files, list_versions
from datakeel.label_drafts import model as draft_model
from datakeel.label_drafts.models import CategorySource, DraftInputs
from datakeel.label_drafts.standards import classify_standards
from datakeel.storage import label_drafts as draft_store
from datakeel.storage.annotation_rows import AnnotationBatchRow
from tests.intents.support import images, plan, run_to_end
from tests.intents.test_label_drafts import RECORDED, label_sets
from tests.production_team_support import ServiceRunner
from tests.standards_support import approved_change

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from datakeel.datasets.views import DatasetView
    from datakeel.storage.database import Database

KINDS = ("圆形灯", "箭头灯", "行人灯", "非机动车灯", "倒计时灯")


def _field(code: str, zh: str, en: str, listing: str) -> FieldStandard:
    return FieldStandard(
        code=code,
        name_zh=zh,
        name_en=en,
        description=f"{en} of a traffic light",
        data_type="string",
        code_list=listing,
        status="active",
    )


def light_contract() -> StandardsContract:
    """Two kind lists (vehicles, traffic lights) and one state list (light colour)."""
    lights = tuple(
        CodeEntry(value=f"k{index}", label_zh=name, label_en=f"Kind {index}")
        for index, name in enumerate(KINDS)
    )
    colours = tuple(
        CodeEntry(value=value, label_zh=zh, label_en=value.title())
        for value, zh in (("red", "红"), ("yellow", "黄"), ("green", "绿"))
    )
    vehicles = (
        CodeEntry(value="car", label_zh="轿车", label_en="Car"),
        CodeEntry(value="bus", label_zh="公交车", label_en="Bus"),
    )
    return StandardsContract(
        standards=(
            _field("vehicle_type", "车辆类型", "Vehicle type", "vehicle_types"),
            _field("light_color", "信号灯颜色", "Traffic light colour", "colours"),
            _field("light_kind", "信号灯类别", "Traffic light kind", "light_kinds"),
        ),
        code_lists=(
            CodeList(code="vehicle_types", name="Vehicle types", status="active", entries=vehicles),
            CodeList(code="colours", name="Colours", status="active", entries=colours),
            CodeList(code="light_kinds", name="Light kinds", status="active", entries=lights),
        ),
    )


def _annotate(db: Database, dataset: DatasetView, labels: list[str]) -> list[str]:
    files = list_files(db, dataset.id)
    version = list_versions(db, dataset.id)[0]
    batch = {
        "annotations": [
            {"sample_id": file.id, "annotator_id": "ann", "labels": [label]}
            for file, label in zip(files, labels, strict=False)
        ]
    }
    with db.session() as session:
        session.add(
            AnnotationBatchRow(
                id=new_id(),
                dataset_id=dataset.id,
                version_id=version.id,
                idempotency_key=new_id(),
                request_digest="generated",
                batch=batch,
                report={},
                created_at=utcnow().timestamp(),
            )
        )
        session.commit()
    return [file.id for file in files[: len(labels)]]


def test_every_kind_list_becomes_a_label_subtree_and_states_become_attributes() -> None:
    """Both kind lists keep their kinds as labels; the colour list attaches to the lights."""
    found = classify_standards(
        light_contract(), ("vehicle_type", "light_color", "light_kind"), "zh"
    )
    parents = {item.key: item.name_zh for item in found.categories if item.parent_key is None}
    assert parents == {"vehicle_type": "车辆", "light_kind": "信号灯"}
    children = [item.name_zh for item in found.categories if item.parent_key == "light_kind"]
    assert children == list(KINDS)
    (colour,) = found.attributes
    assert (colour.key, colour.scope) == ("light_color", "light_kind")
    assert len(found.notes) == 3
    assert any("类型" in note and "物体类别" in note for note in found.notes)
    assert any("颜色" in note and "状态/属性" in note and "信号灯" in note for note in found.notes)


def test_drafted_kinds_are_labels_with_names_attributes_and_recorded_reasons(
    db: Database, tmp_path: Path
) -> None:
    """Each traffic light kind is a child label carrying the colour attribute."""
    approved = approved_change(
        db,
        "import_standards",
        JsonDocument({"contract": light_contract().model_dump(mode="json")}),
    )
    assert approved.status == "SUCCEEDED", approved.error
    dataset = images(db, tmp_path / "images")
    ServiceRunner(db)(
        "draft_label_set",
        {
            "request_id": "lights",
            "name": "信号灯",
            "standard_codes": ["light_color", "light_kind"],
            "dataset_id": dataset.id,
        },
    )
    (drafted,) = label_sets(db)
    kinds = [label for label in drafted.labels if label.name_zh in KINDS]
    assert len(kinds) == len(KINDS)
    assert all(label.parent_id == "light_kind" for label in kinds)
    assert all(
        label.name_en and [f.key for f in label.fields] == ["light_color"] for label in kinds
    )
    assert drafted.draft_source is not None
    assert len(drafted.draft_source.notes) == 2


def test_annotation_only_draft_cites_annotated_samples_as_both_kinds_of_example(
    db: Database, tmp_path: Path
) -> None:
    """Without sample files, examples come from the annotated samples themselves."""
    dataset = images(db, tmp_path / "images")
    red, green, other = _annotate(db, dataset, ["红灯", "绿灯", "绿灯"])
    ServiceRunner(db)(
        "draft_label_set",
        {"request_id": "notes", "name": "信号灯", "annotation_dataset_ids": [dataset.id]},
    )
    (drafted,) = label_sets(db)
    assert drafted.guidelines is not None
    rules = {rule.label_id: rule for rule in drafted.guidelines.rules}
    by_name = {label.name: label.id for label in drafted.labels}
    red_rule = rules[by_name["红灯"]]
    assert {(item.sample_id, item.kind) for item in red_rule.examples} == {
        (red, "positive"),
        (green, "negative"),
        (other, "negative"),
    }
    assert drafted.draft_source is not None
    assert drafted.draft_source.sample_ids == tuple(sorted((red, green, other)))


def _recorded_draft(
    monkeypatch: pytest.MonkeyPatch, budgets: list[float], reply: Mapping[str, object]
) -> None:
    def drafted(
        inputs: DraftInputs, profile: str, budget: float, _client: httpx.Client
    ) -> draft_model.DraftOutcome:
        budgets.append(budget)
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=reply))
        with httpx.Client(transport=transport) as client:
            return draft_model.model_draft(inputs, profile, budget, client)

    monkeypatch.setattr(draft_store, "model_draft", drafted)


def test_planned_budget_counts_the_same_sources_execution_checks(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Repeated annotation categories are one source each, at planning and at execution."""
    monkeypatch.delenv("DATAKEEL_DRAFT_VISION_API_KEY", raising=False)
    monkeypatch.setenv("DATAKEEL_DRAFT_TEXT_API_KEY", "test-only")
    dataset = images(db, tmp_path / "images", count=6)
    _annotate(db, dataset, ["红灯", "绿灯", "红灯", "黄灯", "红灯", "绿灯"])
    result = plan(db, "参考已有标注起草信号灯标签", PageContext(dataset_id=dataset.id))
    assert result.chain is not None
    (step,) = result.chain.steps
    assert step.params["profile"] == "cloud-text"
    expected = draft_model.estimate_cost("cloud-text", 6, 3)
    assert step.params["max_cost_usd"] == expected
    assert step.estimate.cost_usd == expected
    budgets: list[float] = []
    _recorded_draft(monkeypatch, budgets, RECORDED)
    assert run_to_end(db, result.chain).status == "succeeded"
    assert budgets == [expected]


def test_failed_model_answer_is_recorded_with_its_tokens_and_cost(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Thinking is off for structured output; an empty billed answer still leaves a record."""
    monkeypatch.setenv("DATAKEEL_DRAFT_TEXT_API_KEY", "test-only")
    empty = {
        "choices": [{"message": {"content": ""}, "finish_reason": "length"}],
        "usage": {"prompt_tokens": 900, "completion_tokens": 4000},
    }
    sent: list[dict[str, object]] = []

    def reply(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=empty)

    inputs = DraftInputs(name="车辆", categories=(CategorySource(key="car", name_zh="轿车"),))
    with (
        httpx.Client(transport=httpx.MockTransport(reply)) as client,
        pytest.raises(ValidationError, match=r"output_tokens=4000 cost_usd=0\.00"),
    ):
        draft_model.model_draft(inputs, "cloud-text", 0.05, client)
    assert sent[0].get("thinking") == {"type": "disabled"}
    dataset = images(db, tmp_path / "images", count=1)
    _annotate(db, dataset, ["轿车"])
    _recorded_draft(monkeypatch, [], empty)
    plan_ = ServiceRunner(db).plan(
        "draft_label_set",
        {
            "request_id": "empty",
            "name": "车辆",
            "annotation_dataset_ids": [dataset.id],
            "profile": "cloud-text",
            "max_cost_usd": 0.05,
        },
    )
    service.approve_plan(
        db, plan_.id, ApprovalDecision(approve=True, plan_digest=plan_.plan_digest, actor="local")
    )
    with pytest.raises(ValidationError):
        service.execute_plan(
            db, plan_.id, ExecuteRequest(plan_digest=plan_.plan_digest, actor="local")
        )
    (run,) = [item for item in service.list_runs(db) if item.plan_id == plan_.id]
    assert run.status == "FAILED"
    assert run.error is not None
    assert "input_tokens=" in run.error
    assert "cost_usd=" in run.error
    assert label_sets(db) == []
