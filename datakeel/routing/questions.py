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


# A request may end by asking for its own outcome ("..., then tell me how many failed").
_ZH_LINK = re.compile(
    r"[\uff0c,、\uff1b;]\s*(?:然后|接着|随后|之后|完了|完事|做完|弄完|搞完|跑完|最后|并且|并|再|顺便|同时)"
    r"|然后|接着|随后|完了(?:以后|之后)|做完(?:后|之后|以后)|顺便|并且"
    r"|(?:再|并)(?=\s*(?:看|告诉|说|给|列|对比|比较|问|算|报|汇报|返回|统计|数))"
)
_EN_LINK = re.compile(
    r"(?:[,;]\s*|\s+)(?:and\s+then|and|then|after\s+that|afterwards|"
    r"once\s+(?:it['\u2019]?s\s+|that['\u2019]?s\s+)?(?:done|finished))\s+(?:(?:please|pls|also)\s+)?"
    r"(?=(?:tell|show|let|give|report|send|email|share|list|compare|confirm|see|check|how|what|"
    r"which|who|whether|is|are|was|were|did|does|do)\b)",
    re.IGNORECASE,
)
_ASKS = re.compile(
    r"\b(?:who|whom|whose|what|when|where|which|why|how|whether|if)\b|[?\uff1f]|"
    r"多少|几|什么|啥|哪|是否|能否|可否|有没有|([\u4e00-\u9fff])不\1|怎么|怎样|如何|[吗么呢嘛][\s。.!\uff01]*$",
    re.IGNORECASE,
)
# Questions whose focus is the workflow itself, never the outcome of the requested run.
_WORKFLOW_FOCUS = re.compile(
    r"\b(?:approv\w*|sign(?:s|ed)?[\s-]+off|sign-?off|authori[sz]\w*|permission|"
    r"how\s+long|how\s+much\s+time|undo(?:ne)?|revert\w*|roll(?:s|ed)?\s+(?:it\s+)?back|rollback|"
    r"(?:ir)?reversible|(?:last|previous)\s+(?:run|time\s+(?:it|we|you)\s+ran)|"
    r"who\s+(?:approves|signs|authori[sz]es|owns)|"
    r"what\s+(?:it|this|that|the\s+\w+)\s+(?:will|would)\s+(?:do|change|delete|touch))\b|"
    r"审批|批准|审核|签字|签批|授权|权限|谁批|谁审|谁来批|多久|多长时间|多少时间|耗时|"
    r"撤销|撤回|回滚|还原|可逆|上一?次的?(?:结果|运行|执行|跑|清理|体检|变更)|之前那次|"
    r"会做什么|会做哪些|会改什么|会删什么|会不会(?:删|改|动)",
    re.IGNORECASE,
)
_LINK_PUNCTUATION = re.compile(r"^[\s,\uff0c\u3001;\uff1b]+")
# Question words, report verbs and auxiliaries of a result tail ask for the outcome only.
_TAIL_CUES = re.compile(
    r"\b(?:who|whom|whose|what|when|where|which|why|whether|if|"
    r"how(?:\s+(?:many|much|often|well))?|tell\s+me|show\s+me|let\s+me\s+know|give\s+me|"
    r"report(?:\s+back)?|send\s+me|list|is|are|was|were|been|has|have|had|did|does|do)\b|"
    r"[?\uff1f]|已经|曾经|"
    r"多少|几|什么|啥|哪些|哪个|哪|是否|能否|可否|([\u4e00-\u9fff])不\1|怎么样|怎样|如何|"
    r"[吗么呢嘛](?=[\s。.!\uff01]*$)|"
    r"看看|看一下|告诉我|说一下|说说|报一下|给我看|列出来|列出|汇报",
    re.IGNORECASE,
)


def asks_about_workflow(sentence: str) -> bool:
    """Return whether one sentence asks for information rather than requesting execution.

    Args:
        sentence: One sentence of the user's message.

    Returns:
        True for questions about approval, duration, effects, history or ownership, and
        for any interrogative sentence that is not phrased as a polite request. A request
        followed by a linked question about its own outcome stays a request unless that
        question is about the workflow itself.
    """
    text = sentence.strip()
    if not text:
        return False
    split = result_split(text)
    if split is not None:
        return _WORKFLOW_FOCUS.search(text[split:]) is not None
    return _interrogative(text)


def result_split(sentence: str) -> int | None:
    """Locate a linked outcome question that follows an imperative request.

    Args:
        sentence: One sentence of the user's message.

    Returns:
        The offset of the linking word when a non-question request precedes a linked
        question ("..., then tell me how many", "..., 再看看差了多少"), otherwise None.
    """
    links = sorted([*_ZH_LINK.finditer(sentence), *_EN_LINK.finditer(sentence)], key=_start)
    for link in links:
        head, tail = sentence[: link.start()], sentence[link.end() :]
        if (
            len(re.sub(r"\W+", "", head)) > 1
            and not _interrogative(head.strip())
            and _ASKS.search(tail)
        ):
            return link.start()
    return None


def requested_text(text: str) -> str:
    """Blank sentences that ask about a workflow so that only requests can start one.

    Args:
        text: The complete user message.

    Returns:
        The message with every questioning sentence replaced by spaces of equal length;
        in a request with a linked outcome question, only the interrogative and report
        words of that question are blanked.
    """
    return _SENTENCE.sub(_blank_question, text)


def _start(match: re.Match[str]) -> int:
    return match.start()


def _interrogative(text: str) -> bool:
    if _INQUIRY.search(text):
        return True
    if _EN_REQUEST.search(text) or _ZH_REQUEST.search(text):
        return False
    return bool(_EN_QUESTION.search(text) or _ZH_QUESTION.search(text))


def _spaces(match: re.Match[str]) -> str:
    return " " * len(match.group())


def _blank_question(match: re.Match[str]) -> str:
    sentence = match.group()
    split = result_split(sentence)
    if split is not None and _WORKFLOW_FOCUS.search(sentence[split:]) is None:
        # The linked outcome stays in the request's clause; only its question form is blanked.
        tail = _LINK_PUNCTUATION.sub(_spaces, sentence[split:])
        return sentence[:split] + _TAIL_CUES.sub(_spaces, tail)
    return " " * len(sentence) if asks_about_workflow(sentence) else sentence
