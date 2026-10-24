# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Recognize bounded bilingual relationship questions before metric-value parsing."""

import re

from datakeel.core.knowledge_models import KnowledgeIntent
from datakeel.core.models import BoundaryModel


class KnowledgeQuestion(BoundaryModel):
    """Capture the subject phrase instead of matching incidental words in the full question."""

    intent: KnowledgeIntent
    subject: str


_PATTERNS: tuple[tuple[KnowledgeIntent, tuple[str, ...]], ...] = (
    (
        "owned",
        (
            r"(?P<subject>.+?)(?:负责|维护|管理)(?:哪些|什么)(?:指标|数据表|表|数据|资产)?",
            r"what\s+does\s+(?P<subject>.+?)\s+(?:own|maintain|manage)",
            r"which\s+(?:metrics|tables|datasets|assets)\s+does\s+(?P<subject>.+?)\s+(?:own|maintain|manage)",
        ),
    ),
    (
        "owner",
        (
            r"(?P<subject>.+?)(?:的)?(?:负责人|责任人|维护人|维护者|所有者)(?:是)?谁",
            r"(?P<subject>.+?)(?:是)?(?:由谁|谁来|谁)(?:负责|维护|管理)(?:的)?",
            r"(?P<subject>.+?)(?:归谁管|归谁负责)",
            r"谁(?:来)?(?:负责|维护|管理)(?P<subject>.+)",
            r"(?:负责|维护|管理)(?P<subject>.+?)(?:的)?是谁",
            r"who\s+(?:owns|maintains|manages)\s+(?P<subject>.+)",
            r"who\s+is\s+(?:responsible\s+for|the\s+owner\s+of)\s+(?P<subject>.+)",
            r"(?:the\s+)?owner\s+of\s+(?P<subject>.+)",
        ),
    ),
    (
        "upstream",
        (
            r"(?P<subject>.+?)(?:是)?(?:从哪(?:里)?来|来自哪(?:里|儿)|来源于哪(?:里|儿))(?:的)?",
            r"(?P<subject>.+?)(?:的)?上游(?:有)?(?:哪些|什么|是什么|有哪些)?",
            r"(?P<subject>.+?)(?:是)?(?:基于|来自|源于)(?:哪张|哪些|什么)(?:数据)?表(?:计算|算|加工)?(?:出来|而来)?(?:的)?",
            r"(?P<subject>.+?)(?:是)?由(?:什么|哪些|哪张表)(?:加工|计算)(?:而来|出来)?(?:的)?",
            r"where\s+does\s+(?P<subject>.+?)\s+come\s+from",
            r"what\s+is\s+(?P<subject>.+?)\s+(?:derived|computed)\s+from",
            r"(?:the\s+)?upstream(?:\s+(?:tables|datasets))?\s+of\s+(?P<subject>.+)",
            r"what\s+(?:are|is)\s+the\s+upstream(?:\s+tables)?\s+of\s+(?P<subject>.+)",
        ),
    ),
    (
        "downstream",
        (
            r"(?:哪些|什么)(?:指标|数据表|表|视图|数据)(?:是)?(?:用到|使用|基于|依赖)(?P<subject>.+?)(?:计算的|算的|的)?",
            r"(?P<subject>.+?)(?:被|由)(?:哪些|什么)(?:指标|表|数据表|视图)(?:使用|用到|依赖)",
            r"(?P<subject>.+?)(?:的)?下游(?:有)?(?:哪些|什么|是什么|有哪些)?",
            r"what\s+uses\s+(?P<subject>.+)",
            r"which\s+(?:metrics|tables|datasets|views)\s+are\s+(?:computed|derived)\s+from\s+(?P<subject>.+)",
            r"(?:what|which)\s+(?:metrics|tables|datasets|views)\s+(?:use|depend\s+on)\s+(?P<subject>.+)",
            r"(?:the\s+)?downstream(?:\s+(?:tables|metrics))?\s+of\s+(?P<subject>.+)",
        ),
    ),
)


def parse_knowledge_question(question: str) -> KnowledgeQuestion | None:
    """Use complete interrogative templates, preserving metric questions with incidental verbs."""
    text = question.strip().rstrip("?\uff1f。.!\uff01").strip()
    text = re.sub(r"^(?:请问|请告诉我|想知道|麻烦问下)\s*", "", text)
    text = re.sub(
        r"^(?:please\s+tell\s+me|could\s+you\s+tell\s+me)\s+", "", text, flags=re.IGNORECASE
    )
    text = re.sub(r"(?:呢|呀|啊)$", "", text).strip()
    for intent, patterns in _PATTERNS:
        for pattern in patterns:
            match = re.fullmatch(pattern, text, re.IGNORECASE)
            if match is not None:
                subject = re.sub(r"^the\s+", "", match["subject"].strip(), flags=re.IGNORECASE)
                subject = subject.strip(' `"“”「」').removesuffix("的").strip()
                if subject:
                    return KnowledgeQuestion(intent=intent, subject=subject)
    return None
