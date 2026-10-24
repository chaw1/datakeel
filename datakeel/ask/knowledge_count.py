# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Count requested object lists without merging catalog facts and document claims."""

from datakeel.ask.knowledge_focus import QuestionFocus
from datakeel.core.catalog_models import CatalogSnapshot, TableProperties
from datakeel.core.knowledge_models import KnowledgeAnswer, KnowledgeOtherEnd
from datakeel.core.models import AssetRef

_LABELS = {
    "table": "表",
    "view": "视图或汇总",
    "metric": "指标",
    "data": "数据对象",
    "person": "人",
    "team": "团队",
}


def counted_knowledge(
    knowledge: KnowledgeAnswer, focus: QuestionFocus, catalog: CatalogSnapshot
) -> KnowledgeAnswer:
    """Retain only the requested object type while preserving every claim's review state."""
    records = tuple(
        record
        for record in knowledge.system_records
        if _matches_asset(record.asset_ref, focus, catalog)
    )
    claims = tuple(
        claim for claim in knowledge.claims if _matches_other_end(claim.other_end, focus, catalog)
    )
    count = len({(record.asset_ref.asset_type, record.asset_ref.asset_id) for record in records})
    label = _LABELS.get(focus.target_kind or "", "对象")
    return knowledge.model_copy(
        update={
            "system_records": records,
            "claims": claims,
            "system_message": f"系统登记 {count} 个{label}; 仅统计本题所列的当前记录。",
            "reason_code": None
            if records or claims
            else "pending_links"
            if knowledge.pending_ambiguous_links
            else "no_knowledge",
        }
    )


def count_message(
    knowledge: KnowledgeAnswer, focus: QuestionFocus, original: KnowledgeAnswer | None = None
) -> str:
    """State distinct per-section cardinalities without asserting a complete global total."""
    identities = {
        (ref.asset_type, ref.asset_id)
        for claim in knowledge.claims
        for ref in (claim.other_end.asset_ref or claim.other_end.entity.asset_ref,)
    }
    label = _LABELS.get(focus.target_kind or "", "对象")
    message = (
        f"{knowledge.system_message}文档提及 {len(identities)} 个{label}"
        " (按对象去重, 审核状态见列表)。"
    )
    if knowledge.pending_ambiguous_links:
        message += f"另有 {knowledge.pending_ambiguous_links} 条关联待确认, 未计入。"
    if original is not None and focus.target_kind in {"table", "view"}:
        untyped = {
            (claim.other_end.entity.asset_ref.asset_type, claim.other_end.entity.asset_ref.asset_id)
            for claim in original.claims
            if claim.other_end.asset_ref is None and claim.other_end.entity.type == "dataset"
        }
        if untyped:
            message += f"另有 {len(untyped)} 个文档数据对象类型未明, 未计入{label}数量。"
    return message


def _matches_asset(ref: AssetRef, focus: QuestionFocus, catalog: CatalogSnapshot) -> bool:
    kind = ref.asset_type
    if kind == "table":
        item = next(
            (
                item
                for item in catalog.objects
                if item.asset_ref.asset_type == kind and item.asset_ref.asset_id == ref.asset_id
            ),
            None,
        )
        if item is not None and TableProperties.model_validate(item.properties.root).is_view:
            kind = "view"
    return kind in {"table", "view"} if focus.target_kind == "data" else kind == focus.target_kind


def _matches_other_end(
    other: KnowledgeOtherEnd, focus: QuestionFocus, catalog: CatalogSnapshot
) -> bool:
    if other.asset_ref is not None:
        return _matches_asset(other.asset_ref, focus, catalog)
    kind = {"organization": "team", "dataset": "data"}.get(other.entity.type, other.entity.type)
    return (
        kind in {"table", "view", "data"}
        if focus.target_kind == "data"
        else kind == focus.target_kind
    )
