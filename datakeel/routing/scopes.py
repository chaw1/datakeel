# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep workflow signals inside affirmative request clauses rather than prior topics."""

import re

from datakeel.core.models import BoundaryModel
from datakeel.workflows.models import WorkflowDefinition

_CLAUSE = re.compile(r"[^,\uff0c;\uff1b\u3002.!?\uff01\uff1f\n]+")
_NEGATION = re.compile(
    r"\b(?:never|skip|avoid|refrain|cancel(?:ed|led)?|canceling|cancelling)\b|"
    r"\b(?:do|does|did|must|should|will|would|can|could)\s+not\b|"
    r"\bdon['\u2019]t\b|\bnot\s+(?:asking|requesting|run|perform|start|clean|delete|change)\b|"
    r"\bno\s+(?:need|reason|request)\s+to\b|"
    r"\bnot\s+\w+\s+to\s+(?:run|start|perform|clean|change)\b|"
    r"请勿|不要|不再|不必|无需|不用|不想|不能|禁止|不允许|先别|暂时别|暂不|先不|取消|放弃|暂停|暂缓|"
    r"不(?:做|运行|执行|启动|清理|删除|更改|修改)|别(?:做|运行|执行|启动|清理|删除|更改|修改)"
)
_INFO_PREFIX = re.compile(
    r"^\s*(?:(?:please|can you|could you|would you)\s+|请|麻烦|帮我|先)*\s*"
    r"(?:(?:read|view|show|list|display|find|get|tell|describe|explain|look at|bring up|"
    r"regarding|concerning|about)\b|查看|查询|列出|显示|展示|获取|读取|看看|看一下|看|解释|关于)"
)
_READ_INTENT = re.compile(
    r"\b(?:want|need|wish|would\s+like)\s+to\s+(?:read|view|see)\b|"
    r"\b(?:was|were|had|yesterday|previously|completed)\b|已经|曾经|上次|已完成"
)
_RESTRICTION = re.compile(r"\b(?:only|just)\b|仅|只")
_SUBSTEP = re.compile(
    r"\b(?:preprocessing\s+stage|preprocess(?:ing)?\s+only|quarantine|"
    r"measure[- ]column\s+update|current\s+quality\s+score|existing\s+quality\s+score|"
    r"current\s+value|stage|step|phase|part|portion)\b|"
    r"隔离|这一步|环节|阶段|步骤|仅预处理|已有质量分|现有质量分|只.*质量分|仅.*质量分"
)
_KEEP_ORIGINALS = re.compile(r"\bkeep\s+(?:all\s+)?originals\b|保留.*原(?:始)?文件")
_DEFERRED = re.compile(
    r"\b(?:later|eventually|can\s+wait|afterwards)\b|之后再|后续|放到?后面|之后考虑|以后|稍后"
)
_CONTINUATION = re.compile(
    r"\b(?:answer|answers|question|ask|result|results|compare|comparison|contrast|recompute|rerun|"
    r"quality|report|evidence|health|assess(?:ment)?|check|inspect|approval|quarantine|"
    r"delet(?:e|ing|ion))\b|"
    r"答案|结果|比较|对比|对照|再算|重问|再回答|重新问数|再问|健康|评估|检查|体检|质量|报告|证据|隔离|签批|删除"
)


class WorkflowScope(BoundaryModel):
    """Describe one workflow's live request text and original ordering information."""

    text: str = ""
    position: int = 0
    deferred: bool = False


def _has_anchor(text: str, workflow: WorkflowDefinition) -> bool:
    triggers = workflow.triggers
    expressions = [
        *triggers.classification_keywords,
        *triggers.verification_keywords,
        *(group[0] for group in triggers.classification_groups),
    ]
    return any(_literal(text, term) for expression in expressions for term in expression.split("|"))


def _literal(text: str, term: str) -> bool:
    term = " ".join(term.casefold().split())
    prefix = r"(?<![a-z0-9_])" if term[0].isascii() and term[0].isalnum() else ""
    suffix = r"(?![a-z0-9_])" if term[-1].isascii() and term[-1].isalnum() else ""
    return re.search(prefix + re.escape(term) + suffix, text) is not None


def _inactive(text: str) -> bool:
    restricted = _RESTRICTION.search(text) and (
        _SUBSTEP.search(text) or _KEEP_ORIGINALS.search(text)
    )
    return bool(
        _NEGATION.search(text)
        or _INFO_PREFIX.search(text)
        or _READ_INTENT.search(text)
        or _KEEP_ORIGINALS.search(text)
        or restricted
    )


def workflow_scope(
    text: str, workflow: WorkflowDefinition, workflows: list[WorkflowDefinition] | None = None
) -> WorkflowScope:
    """Select affirmative workflow clauses while retaining deferred candidates and offsets."""
    text = text.casefold()
    clauses = tuple(_CLAUSE.finditer(text))
    anchored = any(_has_anchor(clause.group(), workflow) for clause in clauses)
    if not anchored:
        return WorkflowScope(text="" if _inactive(text) else text)
    selected: list[tuple[int, str]] = []
    pending: list[tuple[int, str]] = []
    active = False
    for clause in clauses:
        content = clause.group().strip()
        if _has_anchor(content, workflow):
            active = not _inactive(content)
            if active:
                selected.extend(pending)
                selected.append((clause.start(), content))
            pending = []
        elif any(
            other.id != workflow.id and _has_anchor(content, other) for other in workflows or []
        ):
            active = False
            pending = []
        elif active and _CONTINUATION.search(content):
            selected.append((clause.start(), content))
        elif not _inactive(content) and _CONTINUATION.search(content):
            pending.append((clause.start(), content))
        else:
            active = False
    if not selected:
        return WorkflowScope()
    scoped = ", ".join(content for _, content in selected)
    if _inactive(scoped):
        return WorkflowScope()
    return WorkflowScope(
        text=scoped,
        position=selected[0][0],
        deferred=_DEFERRED.search(scoped) is not None,
    )


def scope_for_workflow(
    text: str, workflow: WorkflowDefinition, workflows: list[WorkflowDefinition] | None = None
) -> str:
    """Return the checked request text for callers that need no ordering metadata."""
    return workflow_scope(text, workflow, workflows).text
