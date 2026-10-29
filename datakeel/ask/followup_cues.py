# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded bilingual grammar for modifying an already resolved metric query."""

import re

from datakeel.core.ask_frame_models import ComparisonMode, TimeGrain

_SWITCH = re.compile(
    r"(?:换成|改成|换为|改为|切换到|改看|换个指标|(?:switch|change|replace)\s+(?:it\s+)?"
    r"(?:to|with)|use\s+|instead\s+)",
    re.IGNORECASE,
)
COMPARISONS: tuple[tuple[ComparisonMode, re.Pattern[str]], ...] = (
    (
        "year_over_year",
        re.compile(
            r"同比|(?:和|与|跟)?\s*去年(?:同期)?(?:相?比|比较)|"
            r"(?:(?:compare(?:d)?\s+(?:it\s+)?(?:with|to)|versus|vs\.?|against)\s+)?"
            r"(?:the\s+)?(?:same\s+(?:period|quarter|month)\s+(?:of\s+)?)?last\s+year"
            r"(?=\s*(?:[?\uff1f!\uff01。,,;\uff1b]|$))|year[ -]over[ -]year|\byoy\b",
            re.IGNORECASE,
        ),
    ),
    (
        "period_over_period",
        re.compile(
            r"环比|(?:和|与|跟)(?:上一期|上期|上个?月|上个?季度)(?:相?比|比较)|"
            r"period[ -]over[ -]period|month[ -]over[ -]month|quarter[ -]over[ -]quarter|"
            r"\b(?:mom|qoq)\b|(?:compare(?:d)?\s+(?:it\s+)?(?:with|to)|versus|vs\.?|against)"
            r"\s+(?:the\s+)?(?:previous|prior)\s+(?:period|month|quarter)",
            re.IGNORECASE,
        ),
    ),
)
SHARE = re.compile(
    r"(?:(?:显示|展示|查看|看)|(?:show(?:\s+me)?|display)\s+(?:the\s+)?)?"
    r"(?:占比|(?<![a-z])(?:shares?|proportions?)(?![a-z]))",
    re.IGNORECASE,
)
_GRAIN_PATTERNS: tuple[tuple[TimeGrain, str], ...] = (
    ("day", r"(?:按照|按|每|逐)天|(?:按照|按|每|逐)日|\b(?:daily|by\s+day|per\s+day)\b"),
    ("month", r"(?:按照|按|每|逐)月|\b(?:monthly|by\s+month|per\s+month)\b"),
    ("quarter", r"(?:按照|按|每|逐)季度|\b(?:quarterly|by\s+quarter|per\s+quarter)\b"),
    ("year", r"(?:按照|按|每|逐)年|\b(?:yearly|annually|by\s+year|per\s+year)\b"),
)
GRAINS: tuple[tuple[TimeGrain, re.Pattern[str]], ...] = tuple(
    (grain, re.compile(pattern, re.IGNORECASE)) for grain, pattern in _GRAIN_PATTERNS
)
SAME_PERIOD = re.compile(
    r"去年同期|(?:the\s+)?same\s+(?:period|quarter|month)\s+last\s+year", re.IGNORECASE
)
_CONTINUATION = re.compile(r"^\s*(?:那么|那|what\s+about|how\s+about|and\s+)", re.IGNORECASE)
_PARTICLE = re.compile(r"呢(?=\s*[?\uff1f。!\uff01]*\s*$)")
_EDIT_CUES = re.compile(
    r"那|呢|再|还有|还是|另外|其他|其它|同样|一样|同期|接着|继续|按照|按|每|逐|拆|分开|去掉|"
    r"只看|只要|换成|改成|换为|改为|切换到|改看|换个|"
    r"\b(?:what\s+about|how\s+about|again|same|also|instead|else|other|another|compared?|"
    r"versus|vs|it|that|those|them|by|per|split|break|switch|change|replace|rather|too|only|"
    r"without|drop|remove)\b",
    re.IGNORECASE,
)
_FILLERS = re.compile(
    r"what\s+about|how\s+about|(?:can|could|would)\s+you|(?:show|give|tell)\s+me|"
    r"\b(?:please|then|now|and|also|instead|switch|change|replace|to|with|use|it|that|"
    r"this|the|by|for|in|what|how|about|look|at|split|break|broken|down|out|view|as)\b|"
    r"那|那么|再|还|呢|吗|呀|啊|请|帮我|看一下|看看|看|一下|拆开|拆分|分开|统计|"
    r"换成|改成|换为|改为|切换到|改看|换个指标|呢|的|是多少|多少|如何|怎么样",
    re.IGNORECASE,
)


def share_spans(question: str, occupied: tuple[tuple[int, int], ...] = ()) -> list[tuple[int, int]]:
    """Locate share presentation outside registered measure names."""
    return [
        hit.span()
        for hit in SHARE.finditer(question)
        if all(hit.end() <= start or hit.start() >= end for start, end in occupied)
    ]


def switch_spans(question: str) -> list[tuple[int, int]]:
    """Locate explicit edit instructions so they cannot be mistaken for arithmetic."""
    return [hit.span() for hit in _SWITCH.finditer(question)]


def continuation_spans(question: str) -> list[tuple[int, int]]:
    """Locate the leading and trailing particles that only announce a follow-up."""
    spans = [hit.span() for hit in (_CONTINUATION.match(question),) if hit is not None]
    particle = _PARTICLE.search(question)
    if particle is not None and all(particle.start() >= end for _, end in spans):
        spans.append(particle.span())
    return spans


def edit_cue(question: str) -> bool:
    """Recognize wording that refers back to the previous query instead of opening a topic."""
    return _EDIT_CUES.search(question) is not None


def metric_switch(question: str) -> bool:
    """Recognize an explicit instruction to replace the metric and retain other slots."""
    continuation = re.search(
        r"^(?:那|那么|what\s+about|how\s+about|and\b)",
        question,
        re.IGNORECASE,
    )
    return _SWITCH.search(question) is not None or continuation is not None


def unknown_followup(question: str, consumed: list[tuple[int, int]]) -> str:
    """Require every meaningful follow-up token to have an understood semantic role."""
    masked = list(question)
    for start, end in consumed:
        masked[start:end] = " " * (end - start)
    remainder = _FILLERS.sub(" ", "".join(masked))
    return re.sub(r"[\s\W_]+", "", remainder)


def comparison_hits(question: str) -> tuple[tuple[ComparisonMode, re.Match[str]], ...]:
    """Exclude bare dates, including their article, from explicit comparison intent."""
    return tuple(
        (mode, hit)
        for mode, pattern in COMPARISONS
        for hit in pattern.finditer(question)
        if re.fullmatch(r"(?:the\s+)?last\s+year", hit.group(), re.IGNORECASE) is None
    )


def conflicting_edits(question: str) -> bool:
    """Clarify incompatible choices or negated edits that do not define a supported operation."""
    comparisons = {mode for mode, _ in comparison_hits(question)}
    grains = {grain for grain, pattern in GRAINS if pattern.search(question)}
    return len(comparisons) > 1 or len(grains) > 1 or _negated_edits(question)


def _negated_edits(question: str) -> bool:
    negation = re.compile(
        r"(?:不要|别|不需要|无需|不想|不用|不|without|no|not|don't|do\s+not|never)"
        r"(?:\s*(?:看|做|显示|统计|采用|使用|进行|show|use|do|want|need|a|the|any))?\s*$",
        re.IGNORECASE,
    )
    patterns = [*(pattern for _, pattern in GRAINS), _SWITCH, SHARE]
    hits = [hit for _, hit in comparison_hits(question)]
    hits.extend(hit for pattern in patterns for hit in pattern.finditer(question))
    negative_suffix = re.compile(r"^\s*(?:不|not\b|is\s+not\b|excluded\b)", re.IGNORECASE)
    return any(negation.search(question[: hit.start()]) for hit in hits) or any(
        negative_suffix.match(question[hit.end() :]) for hit in SHARE.finditer(question)
    )
