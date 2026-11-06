# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Every source kind yields names, attributes and both kinds of example, stated truthfully."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.core.models import new_id, utcnow
from datakeel.dataset_store.dataset_service import list_files, list_versions
from datakeel.label_drafts.complete import offline_draft
from datakeel.label_drafts.model import model_draft
from datakeel.label_drafts.models import CategorySource, DraftInputs, SampleSource
from datakeel.storage.annotation_rows import AnnotationBatchRow
from tests.intents.support import images
from tests.intents.test_label_drafts import label_sets, vehicle_standards
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.core.label_guidelines import LabelGuideline
    from datakeel.core.production_catalog_models import LabelSet
    from datakeel.datasets.views import DatasetView
    from datakeel.storage.database import Database


@pytest.fixture(autouse=True)
def _offline(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("DATAKEEL_DRAFT_TEXT_API_KEY", "DATAKEEL_DRAFT_VISION_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def _kinds(rule: LabelGuideline) -> set[str]:
    cited = {example.kind for example in rule.examples}
    described = {
        kind
        for kind, zh, en in (
            ("positive", "正例(文字说明)", "Positive (described)"),
            ("negative", "反例(文字说明)", "Negative (described)"),
        )
        if zh in rule.text_zh and en in rule.text_en
    }
    return cited | described


def assert_complete(drafted: LabelSet) -> None:
    """Both names, an attribute, a bilingual rule and a positive and a negative example."""
    assert drafted.guidelines is not None
    rules = {rule.label_id: rule for rule in drafted.guidelines.rules}
    for label in drafted.labels:
        assert label.name_zh, label
        assert label.name_en, label
        assert label.fields, label
        rule = rules[label.id]
        assert rule.text_zh, rule
        assert rule.text_en, rule
        assert _kinds(rule) == {"positive", "negative"}, rule


def _cited(drafted: LabelSet) -> int:
    assert drafted.guidelines is not None
    return sum(len(rule.examples) for rule in drafted.guidelines.rules)


def _boxes(db: Database, dataset: DatasetView, labels: list[str]) -> list[str]:
    """Box annotations carrying an occlusion flag and a colour people already filled."""
    files = list_files(db, dataset.id)
    batch = {
        "annotations": [
            {
                "sample_id": file.id,
                "annotator_id": "ann",
                "boxes": [
                    {
                        "category": label,
                        "x1": 1,
                        "y1": 1,
                        "x2": 5,
                        "y2": 5,
                        "attributes": {
                            "occluded": index % 2 == 0,
                            "colour": ["red", "blue"][index % 2],
                        },
                    }
                ],
            }
            for index, (file, label) in enumerate(zip(files, labels, strict=False))
        ]
    }
    with db.session() as session:
        session.add(
            AnnotationBatchRow(
                id=new_id(),
                dataset_id=dataset.id,
                version_id=list_versions(db, dataset.id)[0].id,
                idempotency_key=new_id(),
                request_digest="generated",
                batch=batch,
                report={},
                created_at=utcnow().timestamp(),
            )
        )
        session.commit()
    return [file.id for file in files[: len(labels)]]


def test_standards_only_draft_describes_examples_and_says_so(db: Database) -> None:
    """No sample exists, so examples are described in words and the overview says exactly that."""
    vehicle_standards(db)
    ServiceRunner(db)(
        "draft_label_set",
        {
            "request_id": "std",
            "name": "车辆",
            "standard_codes": ["vehicle_type", "vehicle_occluded"],
        },
    )
    (drafted,) = label_sets(db)
    assert_complete(drafted)
    assert drafted.guidelines is not None
    rules = {rule.label_id: rule for rule in drafted.guidelines.rules}
    # The negative example names the confusable sibling kinds.
    car = next(label for label in drafted.labels if label.name_zh == "轿车")
    assert "「货车」" in rules[car.id].text_zh
    assert "Truck" in rules[car.id].text_en
    assert _cited(drafted) == 0
    overview = drafted.guidelines.overview_zh
    assert "已有标注" not in overview
    assert f"写成文字说明 {2 * len(drafted.labels)} 处" in overview
    assert "written descriptions" in drafted.guidelines.overview_en


def test_sampled_files_without_annotations_still_give_complete_labels(
    db: Database, tmp_path: Path
) -> None:
    """Offline drafting cannot judge images: it names, flags and describes instead of citing."""
    dataset = images(db, tmp_path / "images")
    ServiceRunner(db)(
        "draft_label_set",
        {
            "request_id": "files",
            "name": "路口",
            "topic": "路口",
            "dataset_id": dataset.id,
            "version_id": list_versions(db, dataset.id)[0].id,
            "sample_ids": [file.id for file in list_files(db, dataset.id)],
        },
    )
    (drafted,) = label_sets(db)
    assert_complete(drafted)
    assert drafted.guidelines is not None
    assert [field.key for field in drafted.labels[0].fields] == ["uncertain"]
    overview = drafted.guidelines.overview_zh
    assert "已有标注" not in overview
    assert "先给了「不确定」标记" in overview
    assert "暂无英文名" in overview


def test_annotation_only_draft_takes_attributes_from_what_people_filled(
    db: Database, tmp_path: Path
) -> None:
    """Attributes filled on boxes become typed attribute definitions of their category."""
    dataset = images(db, tmp_path / "images")
    _boxes(db, dataset, ["car", "car", "bus"])
    ServiceRunner(db)(
        "draft_label_set",
        {"request_id": "ann", "name": "车辆", "annotation_dataset_ids": [dataset.id]},
    )
    (drafted,) = label_sets(db)
    assert_complete(drafted)
    fields = {label.name: {f.key: f for f in label.fields} for label in drafted.labels}
    assert set(fields["car"]) == {"occluded", "colour"}
    assert fields["car"]["occluded"].type == "boolean"
    assert fields["car"]["colour"].type == "enum"
    assert [option.value for option in fields["car"]["colour"].options] == ["blue", "red"]
    assert set(fields["bus"]) == {"occluded", "colour"}
    assert drafted.guidelines is not None
    assert f"引用已有标注的样本 {_cited(drafted)} 条" in drafted.guidelines.overview_zh
    assert "模型" not in drafted.guidelines.overview_zh


def test_standards_annotations_and_samples_together_are_complete(
    db: Database, tmp_path: Path
) -> None:
    """A combined draft cites annotated samples where it can and describes the rest."""
    vehicle_standards(db)
    dataset = images(db, tmp_path / "images")
    _boxes(db, dataset, ["car", "truck"])
    ServiceRunner(db)(
        "draft_label_set",
        {
            "request_id": "all",
            "name": "车辆",
            "standard_codes": ["vehicle_type", "vehicle_occluded"],
            "annotation_dataset_ids": [dataset.id],
            "dataset_id": dataset.id,
        },
    )
    (drafted,) = label_sets(db)
    assert_complete(drafted)
    assert drafted.guidelines is not None
    overview = drafted.guidelines.overview_zh
    assert f"引用已有标注的样本 {_cited(drafted)} 条" in overview
    assert "写成文字说明" in overview


def _answer(content: object) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": json.dumps(content)}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 400},
    }


def test_model_draft_overview_states_where_its_examples_really_came_from(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The model's own claim about example sources is replaced by the counted truth."""
    monkeypatch.setenv("DATAKEEL_DRAFT_VISION_API_KEY", "test-only")
    inputs = DraftInputs(
        name="车辆",
        categories=(
            CategorySource(key="car", name_zh="轿车", name_en="Car"),
            CategorySource(key="bus", name_zh="公交车", name_en="Bus"),
        ),
        samples=(
            SampleSource(id="s-1", filename="a.png"),
            SampleSource(id="s-2", filename="b.png"),
        ),
    )
    attribute = {"key": "occluded", "name_zh": "遮挡", "name_en": "Occluded", "type": "boolean"}
    content = {
        "labels": [
            {"id": "car", "name_zh": "轿车", "name_en": "Car", "attributes": [attribute]},
            {"id": "bus", "name_zh": "公交车", "name_en": "Bus", "attributes": [attribute]},
        ],
        "overview_zh": "车辆框。正反例全部来自已有标注。",
        "overview_en": "Vehicle boxes. All examples come from existing annotations.",
        "rules": [
            {
                "label_id": "car",
                "text_zh": "框整车",
                "text_en": "Box the car",
                "positive": [{"sample_id": "s-1"}],
            }
        ],
    }
    reply = httpx.MockTransport(lambda _request: httpx.Response(200, json=_answer(content)))
    with httpx.Client(transport=reply) as client:
        outcome = model_draft(inputs, "cloud-vision", 0.05, client)
    overview = outcome.guidelines.overview_zh
    assert "来自已有标注" not in overview
    assert "车辆框" in overview
    assert "模型看过抽样文件后挑选 1 条" in overview
    assert "写成文字说明 3 处" in overview
    assert "existing annotations" not in outcome.guidelines.overview_en
    rules = {rule.label_id: rule for rule in outcome.guidelines.rules}
    assert "「公交车」" in rules["car"].text_zh
    assert all(label.fields for label in outcome.labels)


def test_offline_overview_never_claims_annotated_examples_it_does_not_have() -> None:
    """The old fixed sentence said examples came from annotations even when none existed."""
    outcome = offline_draft(
        DraftInputs(name="车辆", categories=(CategorySource(key="car", name_zh="轿车"),))
    )
    assert "已有标注" not in outcome.guidelines.overview_zh
    assert "already carry annotations" not in outcome.guidelines.overview_en
