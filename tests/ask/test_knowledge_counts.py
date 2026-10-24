# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Count catalog objects through the knowledge route and retain typed evidence lists."""

from pathlib import Path

import pytest

from datakeel.ask import service
from datakeel.ask.knowledge_claims import document_claims
from datakeel.ask.knowledge_count import count_message, counted_knowledge
from datakeel.ask.knowledge_focus import QuestionFocus
from datakeel.ask.service import ask_data
from datakeel.core.ask_models import AskRequest
from datakeel.core.catalog_models import CatalogSnapshot
from datakeel.core.knowledge_models import KnowledgeAnswer
from datakeel.core.metric_models import CompiledQuery, QueryResult
from datakeel.core.models import JsonDocument
from datakeel.harness.enterprise_kg import seed_enterprise_kg
from datakeel.sample_enterprise import EnterpriseSample
from datakeel.storage.ask_store import get_answer
from datakeel.storage.database import Database
from tests.ask.knowledge_helpers import claim_context, source_reader


def _forbid_query(_connection: str, _query: CompiledQuery) -> QueryResult:
    pytest.fail("Object counts must not execute a business metric query")


@pytest.mark.parametrize(
    ("question", "names", "label"),
    [
        ("orders 表供多少个指标使用", {"零售额", "订单数", "零售量"}, "3 个指标"),
        ("How many metrics depend on orders?", {"零售额", "订单数", "零售量"}, "3 个指标"),
        ("orders 表衍生出几个视图", {"retail_summary"}, "1 个视图或汇总"),
        ("零售额用了多少张表", {"orders"}, "1 个表"),
    ],
)
def test_catalog_count_retains_only_requested_objects_and_never_executes_sql(
    db: Database,
    enterprise_sample: EnterpriseSample,
    monkeypatch: pytest.MonkeyPatch,
    question: str,
    names: set[str],
    label: str,
) -> None:
    """A mixed downstream list counts metrics separately from its derived view."""
    monkeypatch.setattr(service, "execute_query", _forbid_query)
    answer = ask_data(db, AskRequest(question=question))
    assert answer.answer_kind == "knowledge"
    assert answer.status == "answered"
    assert answer.result is None
    assert answer.sql is None
    assert answer.knowledge is not None
    assert {item.name for item in answer.knowledge.system_records} == names
    assert label in answer.message
    assert label in answer.knowledge.system_message
    assert get_answer(db, answer.id) == answer


def test_catalog_count_does_not_claim_global_absence_when_no_records_exist(
    db: Database, enterprise_sample: EnterpriseSample, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty registered list means no recorded evidence, not a business value of zero."""
    monkeypatch.setattr(service, "execute_query", _forbid_query)
    answer = ask_data(db, AskRequest(question="warranties 表影响几个指标"))
    assert answer.answer_kind == "knowledge"
    assert answer.result is None
    assert answer.status == "unanswerable"
    assert answer.knowledge is not None
    assert answer.knowledge.reason_code == "no_knowledge"
    assert "系统登记 0 个指标" in answer.message
    assert "当前记录" in answer.message


def test_person_count_keeps_document_people_separate_from_catalog_roles(
    db: Database, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A responsibility role is not evidence of an additional distinct person."""
    seed_enterprise_kg(db, tmp_path)
    monkeypatch.setattr(service, "execute_query", _forbid_query)
    answer = ask_data(db, AskRequest(question="How many people own customer_count?"))
    assert answer.answer_kind == "knowledge"
    assert answer.knowledge is not None
    assert answer.knowledge.system_records == ()
    assert {claim.other_end.entity.name for claim in answer.knowledge.claims} == {"Leo Fang"}
    assert "系统登记 0 个人" in answer.message
    assert "文档提及 1 个人" in answer.message
    assert all(claim.relation_status == "candidate" for claim in answer.knowledge.claims)


def test_document_object_counts_deduplicate_identity_and_preserve_pending_and_review() -> None:
    """Repeated evidence counts once while every source claim and review receipt survives."""
    subject, context = claim_context()
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    repeated = claims[0].model_copy(update={"assertion_id": "second-source"})
    knowledge = KnowledgeAnswer(
        intent="upstream",
        subject=subject,
        claims=(*claims, repeated),
        pending_ambiguous_links=2,
    )
    focus = QuestionFocus(kind="table", target_kind="table", counted=True)
    catalog = CatalogSnapshot(
        scope="generated", objects=tuple(link.target for link in context.links)
    )
    counted = counted_knowledge(knowledge, focus, catalog)
    assert counted.claims == (*claims, repeated)
    assert counted.pending_ambiguous_links == 2
    assert "文档提及 1 个表" in count_message(counted, focus)
    assert "2 条关联待确认, 未计入" in count_message(counted, focus)


def test_counts_with_only_unresolved_links_preserve_pending_reason() -> None:
    """A zero visible-object count never resolves ambiguous document associations."""
    focus = QuestionFocus(kind="metric", target_kind="metric", counted=True)
    knowledge = KnowledgeAnswer(intent="downstream", pending_ambiguous_links=1)
    result = counted_knowledge(knowledge, focus, CatalogSnapshot(scope="empty"))
    assert result.reason_code == "pending_links"
    assert "未计入" in count_message(result, focus)


def test_team_count_keeps_organizations_and_excludes_people() -> None:
    """People and teams remain distinct even though both use the public person focus."""
    subject, context = claim_context()
    claims, _ = document_claims(subject, "owner", context, set(), source_reader)
    team = claims[0].other_end.entity.model_copy(
        update={
            "name": "Support group",
            "type": "organization",
            "asset_ref": claims[0].other_end.entity.asset_ref.model_copy(
                update={"asset_id": "support-group"}
            ),
        }
    )
    team_claim = claims[0].model_copy(
        update={
            "assertion_id": "team-owner",
            "head": team,
            "other_end": claims[0].other_end.model_copy(update={"entity": team}),
        }
    )
    focus = QuestionFocus(kind="person", target_kind="team", counted=True)
    counted = counted_knowledge(
        KnowledgeAnswer(intent="owner", claims=(*claims, team_claim)),
        focus,
        CatalogSnapshot(scope="empty"),
    )
    assert counted.claims == (team_claim,)
    assert "文档提及 1 个团队" in count_message(counted, focus)


def test_unlinked_document_data_remains_separate_from_catalog_counts() -> None:
    """An unregistered dataset is a document mention and never a catalog fact."""
    subject, context = claim_context()
    context = context.model_copy(update={"links": context.links[:1]})
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    focus = QuestionFocus(kind="table", target_kind="data", counted=True)
    counted = counted_knowledge(
        KnowledgeAnswer(intent="upstream", claims=claims), focus, CatalogSnapshot(scope="empty")
    )
    assert counted.claims == claims
    assert counted.system_records == ()
    assert "系统登记 0 个数据对象" in count_message(counted, focus)
    assert "文档提及 1 个数据对象" in count_message(counted, focus)


@pytest.mark.parametrize("target", ["table", "view"])
def test_unlinked_dataset_cannot_establish_a_table_or_view_count(target: str) -> None:
    """A document dataset with unknown catalog type is disclosed without narrowing its type."""
    subject, context = claim_context()
    context = context.model_copy(update={"links": context.links[:1]})
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    focus = QuestionFocus.model_validate({"kind": "table", "target_kind": target, "counted": True})
    original = KnowledgeAnswer(intent="upstream", claims=(*claims, claims[0]))
    counted = counted_knowledge(original, focus, CatalogSnapshot(scope="empty"))
    assert counted.claims == ()
    assert counted.system_records == ()
    assert counted.reason_code == "no_knowledge"
    assert "文档提及 0 个" in count_message(counted, focus, original)
    assert "另有 1 个文档数据对象类型未明" in count_message(counted, focus, original)


@pytest.mark.parametrize(("target", "expected"), [("table", 0), ("view", 1), ("data", 1)])
def test_linked_document_dataset_uses_its_catalog_view_subtype(target: str, expected: int) -> None:
    """An eligible catalog association supplies the subtype that an unlinked dataset lacks."""
    subject, context = claim_context()
    claims, _ = document_claims(subject, "upstream", context, set(), source_reader)
    view = context.links[1].target.model_copy(
        update={"properties": JsonDocument({"is_view": True})}
    )
    focus = QuestionFocus.model_validate({"kind": "table", "target_kind": target, "counted": True})
    original = KnowledgeAnswer(intent="upstream", claims=claims)
    counted = counted_knowledge(
        original, focus, CatalogSnapshot(scope="generated", objects=(view,))
    )
    assert len(counted.claims) == expected
    assert "类型未明" not in count_message(counted, focus, original)
