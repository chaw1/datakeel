# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compose subject, relation and interrogative clauses before metric-value parsing."""

import re
from typing import Literal

from datakeel.core.knowledge_models import KnowledgeIntent
from datakeel.core.models import BoundaryModel


class KnowledgeQuestion(BoundaryModel):
    """Keep unsupported knowledge wording out of numeric execution."""

    intent: KnowledgeIntent
    subject: str
    unsupported_phrasing: bool = False


_Relation = Literal[
    "own", "owner", "owned_by", "source", "upstream", "depend", "use", "downstream", "feed"
]
_NUMERIC = re.compile(
    r"多少|几|总额|合计|最高|最低|最多|最少|排名|前几|"
    r"\b(?:how\s+(?:much|many)|total|most|least|top)\b",
    re.IGNORECASE,
)
_STRONG = re.compile(
    r"谁|哪位|负责人|上游|下游|来源|依赖|"
    r"\b(?:who|owner|upstream|downstream|source|depends)\b",
    re.IGNORECASE,
)
_ZH_ACTOR = re.compile(
    r"谁|哪位(?:负责人|同事|人员)?|哪个(?:团队|部门)|哪(?:个|些)人|"
    r"(?:团队|部门|人员)(?:是)?(?:哪个|哪位)"
)
_ZH_OBJECT = r"(?:哪(?:张|些|个|种)|什么|哪里|哪儿|哪)"
_ZH_FILL = r"(?:是|的|了|过|都|也|有|在|来|而来|出来|计算|加工|算|得到|组成)*"
_ZH_TARGET = r"(?:数据来源|数据表|数据集|指标|源表|视图|资产|数据|团队|部门|表)*"
_ZH_QUERY = re.compile(rf"{_ZH_FILL}{_ZH_TARGET}{_ZH_FILL}{_ZH_OBJECT}{_ZH_TARGET}{_ZH_FILL}")
_ZH_RELATIONS: tuple[tuple[_Relation, str], ...] = (
    ("owner", r"负责人|责任人|维护人|维护者|所有者"),
    ("own", r"负责|维护|管理|管"),
    ("source", r"来源于|来自|取自|源于"),
    ("depend", r"依赖|基于"),
    ("downstream", r"下游|影响"),
    ("use", r"用到|使用"),
    ("upstream", r"数据来源|数据源|来源(?!于)|源表|上游"),
    ("source", r"从|由|(?<!使)用(?!到)"),
)
_EN_QUERY = re.compile(
    r"^(?:who|where|what|which)\b(?:\s+(?:data\s+sources|source\s+tables|"
    r"metrics|tables|datasets|views|assets|systems|reports|dashboards|sources|"
    r"team|department|person|people))?\s*",
    re.IGNORECASE,
)
_EN_ACTOR = re.compile(r"^(?:who|(?:which|what)\s+(?:team|department|person))\b", re.IGNORECASE)
_EN_RELATIONS: tuple[tuple[_Relation, str], ...] = (
    ("owner", r"(?:data\s+)?owner(?:\s+of)?"),
    ("owned_by", r"(?:owned|maintained|managed)\s+by"),
    ("own", r"owns?|maintains?|manages?|in\s+charge\s+of|responsible\s+for"),
    ("source", r"(?:come[sd]?\s+)?from|(?:derived|computed)\s+from|based\s+on"),
    ("depend", r"depends?\s+on"),
    ("downstream", r"downstream(?:\s+(?:tables|metrics))?(?:\s+of)?|(?:used|consumed)\s+by"),
    ("use", r"uses?|consumes?"),
    ("feed", r"feeds?"),
    ("upstream", r"sources?(?:\s+of)?|upstream(?:\s+(?:tables|datasets))?(?:\s+of)?"),
)
_PUNCTUATION = " \t\n`\"'“”「」『』?\uff1f。.!\uff01,\uff0c:\uff1a;\uff1b"


def parse_knowledge_question(question: str) -> KnowledgeQuestion | None:
    """Prefer explicit quantities, then compose relations, then refuse unsafe fallthrough."""
    if _NUMERIC.search(question):
        return None
    text = _prepare(question)
    for english, relations in ((False, _ZH_RELATIONS), (True, _EN_RELATIONS)):
        for relation, pattern in relations:
            expression = rf"\b(?:{pattern})\b" if english else pattern
            for match in re.finditer(expression, text, re.IGNORECASE):
                before, after = text[: match.start()].strip(), text[match.end() :].strip()
                parsed = (
                    _english(relation, before, after)
                    if english
                    else _chinese(relation, before, after)
                )
                if parsed and _valid_subject(parsed.subject):
                    return parsed
    if _STRONG.search(text):
        return KnowledgeQuestion(intent="related", subject="", unsupported_phrasing=True)
    return None


def _prepare(question: str) -> str:
    text = question.strip(_PUNCTUATION)
    text = re.sub(r"^(?:请问|请告诉我|想知道|麻烦问下|我想知道)\s*", "", text)
    text = re.sub(
        r"^(?:please\s+tell\s+me|(?:could|can|would)\s+you\s+tell\s+me|"
        r"do\s+you\s+know|i(?:'d|\s+would)\s+like\s+to\s+know)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bwho['\u2019]s\b", "who is", text, flags=re.IGNORECASE)
    return re.sub(r"(?:呢|呀|啊)$", "", text).strip()


def _valid_subject(subject: str) -> bool:
    return bool(subject) and not re.search(
        r"谁|哪(?:位|些|张|个|里|儿)|什么|\b(?:who|what|where|which)\b", subject, re.IGNORECASE
    )


def _result(intent: KnowledgeIntent, subject: str) -> KnowledgeQuestion:
    return KnowledgeQuestion(intent=intent, subject=subject.strip(_PUNCTUATION))


def _zh_subject(text: str) -> str:
    text = text.strip(_PUNCTUATION)
    text = re.sub(r"^(?:是|的|了|过|在)+", "", text)
    return re.sub(r"(?:现在|目前|正在|是|的|都|也|由|归|被|在|来|所)+$", "", text).strip(
        _PUNCTUATION
    )


def _zh_query(text: str) -> bool:
    return _ZH_QUERY.fullmatch(re.sub(r"\s+", "", text)) is not None


def _zh_question_subject(text: str) -> str | None:
    """Remove one question clause at either end without consuming the relation's subject."""
    actor = _ZH_ACTOR.search(text)
    if actor:
        left, right = _zh_subject(text[: actor.start()]), _zh_subject(text[actor.end() :])
        return left or right if not (left and right) else None
    for index in range(len(text), 0, -1):
        if _zh_query(text[:index]):
            return _zh_subject(text[index:])
        if _zh_query(text[-index:]):
            return _zh_subject(text[:-index])
    return None


def _chinese(relation: _Relation, before: str, after: str) -> KnowledgeQuestion | None:
    if relation in {"own", "owner"}:
        return _chinese_owner(relation, before, after)
    if relation in ("upstream", "downstream"):
        return _chinese_direction(relation, before, after)
    if relation == "source" and _zh_query(after):
        return _result("upstream", _zh_subject(before))
    if relation in ("depend", "use"):
        return _chinese_dependency(before, after)
    return None


def _chinese_dependency(before: str, after: str) -> KnowledgeQuestion | None:
    left = _zh_subject(before)
    if _zh_query(before):
        reference = re.sub(r"(?:计算|算|加工)(?:出来|而来)?的$", "", after)
        return _result("downstream", _zh_subject(reference))
    if _zh_query(after):
        return _result("upstream", left)
    for question, other in ((before, after), (after, before)):
        if not _zh_subject(other) and (subject := _zh_question_subject(question)) is not None:
            return _result("downstream", subject)
    return None


def _chinese_owner(relation: _Relation, before: str, after: str) -> KnowledgeQuestion | None:
    if relation == "own" and _zh_query(after):
        return _result("owned", _zh_subject(before))
    for question, subject in ((before, after), (after, before)):
        if _ZH_ACTOR.search(question):
            extracted = _zh_question_subject(question)
            if extracted is not None and not (_zh_subject(subject) and extracted):
                return _result("owner", extracted or _zh_subject(subject))
    if relation == "owner" and not after:
        return _result("owner", _zh_subject(before))
    return None


def _chinese_direction(
    relation: Literal["upstream", "downstream"], before: str, after: str
) -> KnowledgeQuestion | None:
    if not after or _zh_query(after):
        subject = _zh_question_subject(before)
        return _result(relation, _zh_subject(before) if subject is None else subject)
    if not before or _zh_query(before):
        return _result(relation, _zh_subject(after))
    return None


def _en_subject(text: str) -> str:
    text = text.strip(_PUNCTUATION)
    text = re.sub(
        r"^(?:(?:is|are|does|do|did|the|a|an|currently)(?:\s+|$))+", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"\s+(?:is|are)$", "", text, flags=re.IGNORECASE)
    return text.removesuffix("'s").removesuffix("\u2019s").strip(_PUNCTUATION)


def _en_question_subject(text: str) -> str | None:
    query = _EN_QUERY.match(text)
    if query:
        return _en_subject(text[query.end() :])
    return None


def _english(relation: _Relation, before: str, after: str) -> KnowledgeQuestion | None:
    left, right = _en_subject(before), _en_subject(after)
    question_left, question_right = _en_question_subject(before), _en_question_subject(after)
    if relation in {"owner", "own", "owned_by"}:
        return _english_owner(relation, before, after)
    if relation in ("upstream", "downstream"):
        return _english_direction(relation, before, after)
    if relation == "feed" and question_left == "":
        return _result("upstream", right)
    if relation in {"source", "depend", "use"}:
        if question_left is not None:
            intent = "upstream" if question_left else "downstream"
            return _result(intent, question_left or right)
        if question_right == "":
            return _result("upstream", left)
    return None


def _english_direction(
    relation: Literal["upstream", "downstream"], before: str, after: str
) -> KnowledgeQuestion | None:
    left, right = _en_subject(before), _en_subject(after)
    question_left, question_right = _en_question_subject(before), _en_question_subject(after)
    if question_left == "" or not left:
        return _result(relation, right)
    if not right or question_right == "":
        return _result(relation, question_left if question_left is not None else left)
    return None


def _english_owner(relation: _Relation, before: str, after: str) -> KnowledgeQuestion | None:
    left, right = _en_subject(before), _en_subject(after)
    question_left = _en_question_subject(before)
    if relation == "owned_by" and question_left == "" and not _EN_ACTOR.match(before):
        return _result("owned", right)
    if _EN_ACTOR.match(before):
        if question_left == "":
            return _result("owner", right)
        if not right and question_left is not None:
            return _result("owner", question_left)
    elif question_left and not right:
        return _result("owned", question_left)
    if _EN_ACTOR.fullmatch(after) and left:
        return _result("owner", left)
    return _result("owner", right) if relation == "owner" and not left else None
