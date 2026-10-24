# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Interpret interrogative types and direction relative to already matched subjects."""

import re
from typing import Literal

from datakeel.ask.knowledge_names import SubjectMention
from datakeel.core.knowledge_models import KnowledgeFocus
from datakeel.core.models import BoundaryModel


class QuestionFocus(BoundaryModel):
    """Keep the question's requested answer type and its observed wording."""

    kind: KnowledgeFocus = "unknown"
    text: str = ""
    start: int = -1


class QuestionDirection(BoundaryModel):
    """Explain which side of a dependency the registered subject occupies."""

    value: Literal["upstream", "downstream"] | None = None
    words: tuple[str, ...] = ()


_ZH_COUNT = r"(?:[一二两三四五六七八九十百零\d]+|几)?"
_EN_FILL = (
    r"(?:(?:is|are)\s+)?(?:the\s+)?"
    r"(?:(?:one|two|three|four|five|six|seven|eight|nine|ten|several|few|all|\d+)\s+)?"
)
_FOCUS: tuple[tuple[KnowledgeFocus, str], ...] = (
    (
        "table",
        (
            rf"哪{_ZH_COUNT}(?:张|些|个|份|种)(?:原始|基础|源|数据)?(?:表|视图|数据)|什么(?:数据)?表|"
            rf"\b(?:which|what)\s+{_EN_FILL}(?:(?:source|data|underlying)\s+)?(?:tables?|views?|datasets?)\b"
        ),
    ),
    (
        "metric",
        (
            rf"哪{_ZH_COUNT}(?:些|个|项|种)(?:(?:排名)?(?:前几|前\d+)|的|\s)*指标|什么指标|"
            rf"\b(?:which|what)\s+{_EN_FILL}(?:(?:top|ranked)\s+\w+\s+)?metrics?\b"
        ),
    ),
    (
        "person",
        (
            rf"谁|哪{_ZH_COUNT}(?:位|些|个|名)(?:同事|人|组|团队|部门|负责人)|哪位|"
            r"(?:团队|部门|人员)(?:是)?哪(?:个|位)|负责人|责任人|所有者|\b(?:who|whose|owner)\b|"
            rf"\b(?:which|what)\s+{_EN_FILL}(?:team|person|people|group|department)\b"
        ),
    ),
    ("location", r"哪(?:里|儿)|从哪|\bwhere\b"),
    ("list", r"(?<!为)什么|哪些|哪几个|怎么|如何|\b(?:what|everything|list|which|how)\b"),
)
_RELATION = re.compile(
    r"负责|维护|分管|管理|归属|上游|下游|来源|源表|来自|取自|依赖|基于|用到|引用|"
    r"\b(?:owns?|owner|maintains?|manages?|responsible|upstream|downstream|sources?|"
    r"depends?|uses?|consumes?|feeds?|derived|computed|built|based)\b"
)
_EXPLICIT = (
    ("downstream", r"下游|\bdownstream\b"),
    ("upstream", r"上游|\bupstream\b"),
)
_DEPENDENCY = re.compile(
    r"依赖|基于|依托|用到|使用|用(?:过|了|着)|用(?=哪|什么|\s)|引用|取自|来自|出自|源于|从|由|"
    r"\b(?:from|based\s+on|depends?\s+on|uses?|used|using|consumes?|consumed|reads?|read)\b"
)
_FEED = re.compile(r"影响|供给|提供给|流向|用于|\b(?:feeds?|sources?\s+for)\b")
_PASSIVE = re.compile(
    r"(?:被|由).*?(?:使用|用到|用过|用了|用着|引用|读取|消费|依赖)|"
    r"\b(?:used|consumed|read|referenced)\s+by\b"
)


def masked_subjects(text: str, mentions: tuple[SubjectMention, ...]) -> str:
    """Hide names so embedded relationship words cannot become grammatical evidence."""
    chars = list(text)
    for item in mentions:
        chars[item.start : item.end] = " " * (item.end - item.start)
    return "".join(chars)


def question_focus(text: str) -> QuestionFocus:
    """Prefer typed interrogatives over generic list and relationship descriptors."""
    for kind, pattern in _FOCUS:
        if hit := re.search(pattern, text):
            return QuestionFocus(kind=kind, text=hit.group(), start=hit.start())
    return QuestionFocus()


def has_relation(text: str) -> bool:
    """Recognize bounded relation phrases, never single-character word fragments."""
    return _RELATION.search(text) is not None


def question_direction(
    text: str, mention: SubjectMention, focus: QuestionFocus
) -> QuestionDirection:
    """Use dependency position and passive voice; explicit direction takes precedence."""
    for value, pattern in _EXPLICIT:
        if hit := re.search(pattern, text):
            return QuestionDirection(
                value="upstream" if value == "upstream" else "downstream", words=(hit.group(),)
            )
    if hit := _PASSIVE.search(text):
        actor = (
            hit.start() < mention.start < hit.end()
            if hit.group().startswith(("被", "由"))
            else mention.start >= hit.end()
        )
        return QuestionDirection(
            value="upstream" if actor else "downstream",
            words=tuple(part for part in re.split(r"\s{2,}", hit.group()) if part),
        )
    if hit := re.search(r"(?:被|由).*?(?:生成|加工|计算|产出|汇总)", text):
        inside = hit.start() < mention.start < hit.end()
        return QuestionDirection(value="downstream" if inside else "upstream", words=(hit.group(),))
    return _verb_direction(text, mention, focus)


def _verb_direction(text: str, mention: SubjectMention, focus: QuestionFocus) -> QuestionDirection:
    if hit := _FEED.search(text):
        before = mention.end <= hit.start()
        return QuestionDirection(value="downstream" if before else "upstream", words=(hit.group(),))
    if hit := _DEPENDENCY.search(text):
        # In both languages the object after from/use is the input; the subject before it
        # is the output. A fronted interrogative does not change that grammatical role.
        after = mention.start >= hit.end() and not (hit.end() <= focus.start < mention.start)
        return QuestionDirection(value="downstream" if after else "upstream", words=(hit.group(),))
    if hit := re.search(r"来源|源表|数据源|\bsources?\b", text):
        return QuestionDirection(value="upstream", words=(hit.group(),))
    if re.search(r"怎么算|怎么.*算|如何.*(?:算|计算)", text):
        return QuestionDirection(value="upstream", words=(focus.text,))
    return QuestionDirection()
