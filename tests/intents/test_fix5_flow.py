# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""FIX5: the flow checks what the model left open before a sentence ends.

Every sentence here is written for the FIX3 development world (North Crossing, 南区车道);
none comes from a regression or blind set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from datakeel.core.intent_models import IntentResult, PageContext
from datakeel.core.release_models import ReleaseView
from datakeel.intents.catalog import EntityCatalog
from datakeel.intents.public_text import public_result
from datakeel.storage.production_catalog_rows import ProductionLabelSetRow
from tests.intents.fix3_support import planned, shown, steps, targets, two_projects
from tests.production_team_ops import save
from tests.production_team_support import ServiceRunner

if TYPE_CHECKING:
    import pytest

    from datakeel.storage.database import Database


def _none(**fields: object) -> dict[str, object]:
    return {"kind": "none", "reason": "recorded", **fields}


def test_an_action_that_fits_but_misses_a_value_is_asked_with_choices(db: Database) -> None:
    """A "none" naming the action that does it becomes that action's question (11.2-1)."""
    two_projects(db)
    fits = _none(related=["publish_label_set", "create_label_set"], fits="publish_label_set")
    asked = planned(db, "把那套标签定下来", [fits], PageContext())
    assert asked.kind == "clarify", asked.text
    assert asked.clarification is not None
    assert asked.clarification.candidates, asked.text
    assert "平台没有" not in asked.text
    # A single name in "choose" is no choice: the words fit that action.
    single = _none(choose=["publish_label_set"], related=["publish_label_set"])
    alone = planned(db, "Publish that label set", [single], PageContext())
    assert alone.kind == "clarify", alone.text
    assert alone.clarification is not None
    assert alone.clarification.candidates


def test_an_action_that_fits_but_the_speaker_may_not_run_is_refused(db: Database) -> None:
    """The registered action exists, the speaker lacks its permission: a refusal, why."""
    _, south, _ = two_projects(db)
    fits = _none(
        related=["upgrade_project"],
        fits="upgrade_project",
        steps=[{"id": "s1", "action": "upgrade_project", "params": {"project_id": south.id}}],
    )
    refused = planned(db, "南区车道换成团队档吧", [fits], PageContext(), actor="wang")
    assert refused.kind == "refuse", refused.text
    assert refused.missing_scopes


def test_only_a_request_nothing_registered_does_is_said_missing(db: Database) -> None:
    """No fitting action (or one the registry lacks): the feature is missing, never a question."""
    two_projects(db)
    close = _none(related=["configure_project"])
    missing = planned(db, "给南区车道定个交付截止日", [close], PageContext())
    assert missing.kind == "unsupported", missing.text
    assert "平台没有这个功能" in missing.text
    invented = _none(related=["configure_project"], fits="set_deadline")
    still = planned(db, "Give 南区车道 a delivery deadline", [invented], PageContext())
    assert still.kind == "unsupported", still.text
    assert "平台没有这个功能" in still.text


def test_a_change_that_is_already_so_names_the_current_state(db: Database) -> None:
    """Already disabled, already with that reviewer, never quarantined: said, no card (11.2-4)."""
    _, south, _ = two_projects(db)
    disable = {"operation": "update", "user_id": "li", "status": "disabled"}
    ServiceRunner(db)("manage_users", disable, "boss")
    off = ("manage_users", disable)
    account = planned(db, "小李这个号关掉", [steps(off)], PageContext())
    assert account.kind == "answer", account.text
    assert "小李" in account.text
    assert "已停用" in account.text
    review = {"task_ids": {"$tasks": {"numbers": [3]}}, "actor": "zhao", "stage": "review"}
    page = PageContext(project_id=south.id)
    held = planned(db, "#3 让小赵来审", [steps(("assign_tasks", review))], page)
    assert held.kind == "answer", held.text
    assert "小赵手上审核" in held.text
    files = {"selection": {"$files": {"kind": "named", "names": ["1.png"]}}}
    data = PageContext(dataset_id=south.dataset_id)
    free = planned(db, "1.png 解除隔离", [steps(("unquarantine_files", files))], data)
    assert free.kind == "answer", free.text
    assert "本来就没被隔离" in free.text


def test_a_question_about_objects_always_offers_choices(db: Database) -> None:
    """Two values missing, one an object: the object comes with its choices (11.2-7)."""
    two_projects(db)
    bare = planned(db, "把项目升个档位", [steps(("upgrade_project", {}))], PageContext())
    assert bare.kind == "clarify", bare.text
    assert bare.clarification is not None
    offered = {item.label for item in bare.clarification.candidates}
    assert {"North Crossing", "南区车道"} <= offered, bare.text
    assert bare.clarification.fields == ["project_id"]


def _models(db: Database) -> None:
    run = ServiceRunner(db)
    for model, name, kind in (("box-1", "Boxer", "box"), ("shape-1", "Shaper", "polygon")):
        payload = {"id": model, "name": name, "version": "1.0", "provider": "fake"}
        run("register_model", {"model": {**payload, "capabilities": [kind]}}, "boss")


def test_a_model_named_in_the_words_is_asked_for(db: Database) -> None:
    """Naming the model answers "should a model do it" (11.2-9)."""
    _, south, _ = two_projects(db)
    _models(db)
    run = ("run_prelabel", {"project_id": south.id, "model_id": "Boxer"})
    named = planned(db, "先让 Boxer 把南区车道过一遍", [steps(run)], PageContext())
    assert named.kind == "plan", named.text
    english = planned(db, "Have Boxer go over 南区车道 first", [steps(run)], PageContext())
    assert english.kind == "plan", english.text


def test_a_model_update_reads_its_revision_from_the_catalog(db: Database) -> None:
    """The expected revision of a model change is derived, never asked (11.2-8)."""
    two_projects(db)
    _models(db)
    bump = ("update_model", {"model": "Boxer", "version": "1.1"})
    updated = planned(db, "Boxer 出了 1.1, 把我们这边的也换上", [steps(bump)], PageContext())
    assert updated.kind == "plan", updated.text
    assert updated.chain is not None
    params = updated.chain.steps[0].params
    assert params["expected_revision"] == 1
    model = params["model"]
    assert isinstance(model, dict)
    assert model["id"] == "box-1"
    assert model["version"] == "1.1"
    assert model["capabilities"] == ["box"]


def test_a_model_that_cannot_do_the_step_is_said_not_asked(db: Database) -> None:
    """Capability mismatch: "cannot" with the reason and the alternative, no question (11.2-5)."""
    north, _, _ = two_projects(db)
    _models(db)
    shaped = ("run_prelabel", {"project_id": north.id, "model_id": "Shaper"})
    alone = planned(db, "Shaper 帮 North Crossing 先预标一下", [steps(shaped)], PageContext())
    assert alone.kind == "answer", alone.text
    assert "做不了" in alone.text
    assert "Boxer" in alone.text
    assert "吗" not in alone.text
    english = planned(db, "Let Shaper pre-label North Crossing", [steps(shaped)], PageContext())
    assert english.kind == "answer", english.text
    assert "cannot be done" in english.text


def test_a_place_is_counted_as_shown_and_protection_never_moves_it(db: Database) -> None:
    """The place 第一个包最后那条 is that task even when protection would leave it out (11.2-6)."""
    _, south, tasks = two_projects(db)
    save(db, tasks[1], "wang")
    group = {"holder": "wang", "package": {"$nth": 1}, "last": 1}
    revoke = ("revoke_assignment", {"task_id": {"$tasks": group}, "reason": "太慢"})
    page = PageContext(project_id=south.id)
    result = planned(db, "第一个包最后那条小王一直没交, 收回", [steps(revoke)], page)
    assert result.kind == "plan", result.text
    assert targets(result) == [tasks[1]]
    assert "已有人工标注" in shown(result).get("提醒", ""), shown(result)


def test_a_release_tag_names_the_version_it_published(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dataset name with a release tag (v3.1.0) is the version that release froze (11.2-2)."""
    _, south, _ = two_projects(db)
    tagged = ReleaseView.model_construct(
        id="r-9", dataset_id=south.dataset_id, version_id=south.version_id, tag="v3.1.0"
    )

    def releases(_db: Database, dataset: str) -> list[ReleaseView]:
        return [tagged] if dataset == south.dataset_id else []

    monkeypatch.setattr("datakeel.intents.catalog.list_releases", releases)
    create = {
        "name": "复核三期",
        "dataset_id": south.dataset_id,
        "version_id": "Generated production v3.1.0",
        "label_set_id": south.label_set_id,
    }
    said = "用 Generated production v3.1.0 那版开个项目叫「复核三期」"
    result = planned(db, said, [steps(("create_project", create))], PageContext())
    assert result.kind == "plan", result.text
    assert result.chain is not None
    assert result.chain.steps[0].params["version_id"] == south.version_id


def test_a_project_on_a_label_set_never_published_says_what_to_do_first(db: Database) -> None:
    """Preconditions are checked when planning: publish first, said before any card (11.2-3)."""
    _, south, _ = two_projects(db)
    with db.session() as session:
        db.lock_writes(session)
        first = session.get(ProductionLabelSetRow, f"{south.label_set_id}:1")
        assert first is not None
        payload = {**first.payload, "id": "cones", "name": "锥桶", "published": False}
        row = ProductionLabelSetRow(
            id="cones:1", label_set_id="cones", version=1, published=False, payload=payload
        )
        session.add(row)
        session.commit()
    create = {
        "name": "锥桶标注",
        "dataset_id": south.dataset_id,
        "version_id": south.version_id,
        "label_set_id": "cones",
    }
    said = "用这个数据集开个锥桶标注项目, 标签用锥桶那套"
    page = PageContext(dataset_id=south.dataset_id)
    asked = planned(db, said, [steps(("create_project", create))], page)
    assert asked.kind == "clarify", asked.text
    assert "还没有发布过" in asked.text
    assert "先发布" in asked.text


def test_the_persons_own_words_quoted_back_are_not_internal_names() -> None:
    """A verbatim quote of the request passes the outward check; other English does not."""
    request = "Publish the cones draft and email the whole team about it"
    quoted = "已发布。另外「email the whole team about it」没有做: 平台上没有能做这件事的操作。"
    result = IntentResult(kind="answer", text=quoted, request=request)
    assert public_result(result, "zh", EntityCatalog()).text == quoted
    other = IntentResult(kind="answer", text="另外「notify the team」没有做。", request="发布它")
    assert public_result(other, "zh", EntityCatalog()).text != other.text
