# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Draft output room, field-name repair and the spend of every billed drafting call."""

from __future__ import annotations

import contextlib
import json
from decimal import Decimal
from typing import TYPE_CHECKING

import httpx
import pytest

from datakeel.actions import service
from datakeel.actions.models import ApprovalDecision, ExecuteRequest
from datakeel.core.errors import ValidationError
from datakeel.core.label_guidelines import BilledDraftError
from datakeel.dataset_store.dataset_service import list_files, list_versions
from datakeel.label_drafts import model as draft_model
from datakeel.label_drafts.model import estimate_cost, model_draft, output_tokens
from datakeel.label_drafts.models import CategorySource, DraftInputs, SampleSource
from datakeel.storage import label_drafts as draft_store
from datakeel.storage.harness_service import summarize_costs
from tests.intents.support import images
from tests.intents.test_label_drafts import label_sets
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    from pathlib import Path

    from datakeel.storage.database import Database


def _inputs(count: int = 2) -> DraftInputs:
    kinds = [("car", "轿车", "Car"), ("bus", "公交车", "Bus")]
    kinds += [(f"k{index}", f"类{index}", f"Kind {index}") for index in range(count - 2)]
    return DraftInputs(
        name="车辆",
        categories=tuple(CategorySource(key=k, name_zh=zh, name_en=en) for k, zh, en in kinds),
        samples=(
            SampleSource(id="s-1", filename="a.png"),
            SampleSource(id="s-2", filename="b.png"),
        ),
    )


def _reply(content: str, *, finish: str = "stop", tokens: int = 400) -> dict[str, object]:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": finish}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": tokens},
    }


GOOD = json.dumps(
    {
        "labels": [
            {
                "id": "car",
                "name_zh": "轿车",
                "name_en": "Car",
                "attributes": [
                    {"key": "occluded", "name_zh": "遮挡", "name_en": "Occluded", "type": "boolean"}
                ],
            }
        ],
        "rules": [
            {
                "label_id": "car",
                "text_zh": "框整车",
                "text_en": "Box the car",
                "positive": [{"sample_id": "s-1"}],
                "negative": [{"sample_id": "s-2"}],
            }
        ],
    }
)


def _run(
    monkeypatch: pytest.MonkeyPatch, replies: list[dict[str, object]], inputs: DraftInputs
) -> tuple[draft_model.DraftOutcome, list[dict[str, object]]]:
    monkeypatch.setenv("DATAKEEL_DRAFT_TEXT_API_KEY", "test-only")
    sent: list[dict[str, object]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=replies[min(len(sent), len(replies)) - 1])

    with httpx.Client(transport=httpx.MockTransport(answer)) as client:
        return model_draft(inputs, "cloud-text", 0.5, client), sent


def test_output_room_and_the_estimate_grow_with_the_label_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A large tree gets more output tokens than the old fixed 4000, and the plan pays for it."""
    assert output_tokens(2) == 4700
    assert output_tokens(16) == 7900 > output_tokens(2)
    assert output_tokens(200) == draft_model.OUTPUT_MAX
    assert estimate_cost("cloud-text", 2, 16) > estimate_cost("cloud-text", 2, 2)
    _, sent = _run(monkeypatch, [_reply(GOOD)], _inputs(16))
    assert sent[0]["max_tokens"] == output_tokens(16)


def test_misspelt_field_names_are_mapped_without_another_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Read key for id, name_cn, id for an attribute key and plain option strings are all read."""
    slipped = {
        "labels": [
            {
                "key": "car",
                "name_cn": "轿车",
                "en_name": "Car",
                "attrs": [
                    {
                        "id": "colour",
                        "name_cn": "颜色",
                        "name_en": "Colour",
                        "type": "enum",
                        "values": ["red", "blue"],
                    }
                ],
            }
        ],
        "rules": [
            {
                "label": "car",
                "rule_zh": "框整车",
                "rule_en": "Box the car",
                "positives": ["s-1"],
                "negatives": [{"id": "s-2", "reason": "公交"}],
            }
        ],
    }
    outcome, sent = _run(monkeypatch, [_reply(json.dumps(slipped))], _inputs())
    assert len(sent) == 1
    car = next(label for label in outcome.labels if label.id == "car")
    (colour,) = car.fields
    assert colour.key == "colour"
    assert [option.value for option in colour.options] == ["red", "blue"]
    rule = next(rule for rule in outcome.guidelines.rules if rule.label_id == "car")
    assert rule.text_zh.startswith("框整车")
    assert {(item.sample_id, item.kind) for item in rule.examples} == {
        ("s-1", "positive"),
        ("s-2", "negative"),
    }


def test_a_cut_off_answer_is_repaired_once_with_more_room_and_both_calls_counted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The second request carries the broken answer and its problems instead of discarding it."""
    cut = GOOD[: len(GOOD) // 2]
    replies = [_reply(cut, finish="length", tokens=4700), _reply(GOOD)]
    outcome, sent = _run(monkeypatch, replies, _inputs())
    assert len(sent) == 2
    first, repair = sent
    assert repair["max_tokens"] == min(draft_model.OUTPUT_MAX, 2 * int(str(first["max_tokens"])))
    messages = repair["messages"]
    assert isinstance(messages, list)
    assert messages[1] == {"role": "assistant", "content": cut}
    assert "cut off" in json.dumps(messages[2])
    assert [call.purpose for call in outcome.calls] == ["draft", "repair"]
    assert outcome.input_tokens == 2000
    assert outcome.output_tokens == 5100
    assert outcome.cost_usd == round(sum(call.cost_usd for call in outcome.calls), 6)
    assert {label.id for label in outcome.labels} == {"car", "bus"}


def test_unreadable_items_are_listed_for_the_repair_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """A label without any name is not silently dropped: the model is asked to fix it."""
    broken = json.dumps({"labels": [{"id": "car"}, {"id": "bus", "name_zh": "公交车"}]})
    _, sent = _run(monkeypatch, [_reply(broken), _reply(GOOD)], _inputs())
    assert len(sent) == 2
    problems = json.dumps(sent[1]["messages"], ensure_ascii=False)
    assert "labels[0]: name_zh" in problems


def test_two_unusable_answers_fail_with_every_billed_call_attached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The error carries the calls themselves, not only their numbers in its text."""
    with pytest.raises(BilledDraftError) as raised:
        _run(monkeypatch, [_reply("", finish="length", tokens=4700)], _inputs())
    assert [call.purpose for call in raised.value.calls] == ["draft", "repair"]
    assert all(call.cost_usd > 0 for call in raised.value.calls)


def _plan(db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reply: object) -> str:
    monkeypatch.setenv("DATAKEEL_DRAFT_TEXT_API_KEY", "test-only")
    dataset = images(db, tmp_path / "images", count=1)

    def drafted(
        inputs: DraftInputs, profile: str, budget: float, _client: httpx.Client
    ) -> draft_model.DraftOutcome:
        transport = httpx.MockTransport(lambda _request: httpx.Response(200, json=reply))
        with httpx.Client(transport=transport) as client:
            return model_draft(inputs, profile, budget, client)

    monkeypatch.setattr(draft_store, "model_draft", drafted)
    plan = ServiceRunner(db).plan(
        "draft_label_set",
        {
            "request_id": "spend",
            "name": "车辆",
            "dataset_id": dataset.id,
            "version_id": list_versions(db, dataset.id)[0].id,
            "sample_ids": [file.id for file in list_files(db, dataset.id)],
            "profile": "cloud-text",
            "max_cost_usd": 0.5,
        },
    )
    service.approve_plan(
        db, plan.id, ApprovalDecision(approve=True, plan_digest=plan.plan_digest, actor="local")
    )
    with contextlib.suppress(ValidationError):
        service.execute_plan(
            db, plan.id, ExecuteRequest(plan_digest=plan.plan_digest, actor="local")
        )
    return plan.id


def test_failed_draft_calls_reach_the_cost_summary(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A draft rolled back after two billed calls still shows both in the spend summary."""
    reply = _reply("", finish="length", tokens=4700)
    plan_id = _plan(db, tmp_path, monkeypatch, reply)
    (run,) = [item for item in service.list_runs(db) if item.plan_id == plan_id]
    assert run.status == "FAILED"
    assert label_sets(db) == []
    summaries = [item for item in summarize_costs(db) if item.key == plan_id]
    assert len(summaries) == 1, summarize_costs(db)
    (summary,) = summaries
    assert summary.calls == 2
    assert summary.output_tokens == 2 * 4700
    assert summary.cost_usd > Decimal(0)
    (by_model,) = summarize_costs(db, "model")
    assert by_model.key == "deepseek-flash"


def test_successful_draft_calls_are_in_the_cost_summary_too(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stored version and the spend summary report the same single call."""
    answer = json.loads(GOOD)
    # The draft's own name is its root label when no source names a category.
    answer["labels"].append({"id": "车辆", "name_zh": "车辆", "name_en": "Vehicles"})
    plan_id = _plan(db, tmp_path, monkeypatch, _reply(json.dumps(answer)))
    (drafted,) = label_sets(db)
    assert drafted.draft_source is not None
    summaries = [item for item in summarize_costs(db) if item.key == plan_id]
    assert len(summaries) == 1, summarize_costs(db)
    (summary,) = summaries
    assert summary.calls == 1
    assert summary.cost_usd == Decimal(str(drafted.draft_source.cost_usd))
