# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Separate requests to run a workflow from questions asked about the workflow itself."""

import re

_SENTENCE = re.compile(r"[^。.!\uff01?\uff1f;\uff1b\n]+[。.!\uff01?\uff1f;\uff1b\n]*")
_LEAD = (
    r"^\s*(?:(?:so|and|but|hey|hi|ok|okay|well|also|then|now|quick\s+question|btw)\b"
    r"[\s,\uff0c:]*)*"
)
_SUBJECT = r"(?:i|we|you|they|it|he|she|there|this|that|these|those)"
_EN_REQUEST = re.compile(
    _LEAD + r"(?:please|pls|kindly|go\s+ahead|let['\u2019]?s|let\s+us|"
    r"(?:can|could|would|will)\s+(?:you|u)(?!\s+(?:tell|explain|describe|confirm|say)\b)|"
    r"(?:can|could|shall)\s+we|(?:would|do)\s+you\s+mind|any\s+chance\s+you|"
    r"how\s+about|what\s+about|why\s+not|why\s+don['\u2019]?t\s+(?:you|we)|"
    r"(?:is|would)\s+it\s+(?:be\s+)?possible\s+(?:for\s+you\s+)?to(?!\s+(?:undo|reverse))|"
    r"i\s+(?:want|need|would\s+like|['\u2019]d\s+like)\s+(?:you\s+)?to"
    r"(?!\s+(?:know|understand|learn|ask|find\s+out|see\s+(?:if|whether))))\b",
    re.IGNORECASE,
)
_EN_QUESTION = re.compile(
    _LEAD + r"(?:(?:who|whom|whose|what|when|where|which|why|how|does|did|is|are|was|were|am|"
    r"will|would|should|shall|can|could|may|might|must|has|had|[a-z]+n['\u2019]t)\b|"
    rf"(?:do|have)\s+{_SUBJECT}\b|(?:do|have)\b.*\?\s*$)",
    re.IGNORECASE,
)
_ZH_REQUEST = re.compile(
    r"^\s*(?:请(?!问|教)|麻烦|帮我|帮忙|给我|你(?:能|可以|来|去|帮)|"
    r"(?:能|可以|可不可以|能不能|能否|是否可以)(?:请你|麻烦你|你)?)"
)
_ZH_QUESTION = re.compile(
    r"[吗么呢嘛][\s。?\uff1f!\uff01]*$|([一-鿿])不\1|"
    r"谁|什么|啥|哪|多久|多长|多少|(?<![这那前后好])几(?:分钟|个?小时|天|步|次|秒|个?步骤)|"
    r"怎么|怎样|如何|为何|为什么|为啥|是否|请问|请教"
)
_INQUIRY = re.compile(
    r"\b(?:how\s+(?:long|much\s+time|many\s+steps|soon)|whether|"
    r"(?:want|like|need|wish)\s+to\s+(?:know|understand|learn|find\s+out|ask)|"
    r"wonder(?:ing)?|curious)\b|"
    r"多久|多长时间|多少时间|耗时|想知道|想了解|想问|问一下|请问|请教|好奇|需不需要|要不要|会不会",
    re.IGNORECASE,
)


def asks_about_workflow(sentence: str) -> bool:
    """Return whether one sentence asks for information rather than requesting execution.

    Args:
        sentence: One sentence of the user's message.

    Returns:
        True for questions about approval, duration, effects, history or ownership, and
        for any interrogative sentence that is not phrased as a polite request.
    """
    text = sentence.strip()
    if not text:
        return False
    if _INQUIRY.search(text):
        return True
    if _EN_REQUEST.search(text) or _ZH_REQUEST.search(text):
        return False
    return bool(_EN_QUESTION.search(text) or _ZH_QUESTION.search(text))


def requested_text(text: str) -> str:
    """Blank sentences that ask about a workflow so that only requests can start one.

    Args:
        text: The complete user message.

    Returns:
        The message with every questioning sentence replaced by spaces of equal length.
    """
    return _SENTENCE.sub(_blank_question, text)


def _blank_question(match: re.Match[str]) -> str:
    sentence = match.group()
    return " " * len(sentence) if asks_about_workflow(sentence) else sentence
