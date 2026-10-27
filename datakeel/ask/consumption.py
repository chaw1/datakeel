# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find time, filter and grouping fragments that no deterministic parser consumed."""

import re

from datakeel.ask.models import Leftovers
from datakeel.ask.time_vocabulary import CAPITAL_MAY, TIME_LIKE

_MASK = "#"
_NUMBER = re.compile(r"\d+")
_TIME_PREPOSITION = re.compile(
    r"(?<![a-z#])(?:during|throughout|since|until|till|before|after|around|prior\s+to|"
    r"ahead\s+of|following|preceding)\s+(?:(?:the|our|this|that|these|those|a|an)\s+)*"
    r"[a-z][a-z0-9'\u2019-]*",
    re.IGNORECASE,
)
_MODIFIER_BEFORE = re.compile(
    r"(?:(?<![a-z])(?:around|about|approximately|approx\.?|roughly|circa|near|nearly|almost|"
    r"before|after|prior\s+to|ahead\s+of|following|preceding|excluding|except|other\s+than|"
    r"outside(?:\s+of)?|not\s+in)|大约|大概|约|将近|接近|除了|除|不含|不包括)\s*$",
    re.IGNORECASE,
)
_MODIFIER_AFTER = re.compile(r"^\s*(?:之前|以前|之后|以后|左右|前后|上下|以外|之外|除外|前|后)")
_EN_CONDITION = re.compile(
    r"(?<![a-z#])(?P<cue>in|for|from|at|within|inside|among|across|by|per|each|every|excluding|"
    r"except|without|outside|only|via|under|over|above|below|between|whose|where|with)\s+"
    r"(?:(?:the|our|all|a|an|its|their|this|that|these|those|each|every|of)\s+)*"
    r"(?P<word>[a-z][a-z0-9'\u2019-]*)",
    re.IGNORECASE,
)
_NEUTRAL = frozenset(
    {
        "total",
        "totals",
        "general",
        "overall",
        "aggregate",
        "sum",
        "company",
        "business",
        "us",
        "me",
        "short",
        "particular",
        "detail",
        "details",
        "number",
        "numbers",
        "figure",
        "figures",
        "value",
        "values",
        "rmb",
        "cny",
        "yuan",
        "which",
        "what",
        "how",
        "whole",
        "entire",
        "full",
        "it",
        "them",
    }
)
_CALCULATION = re.compile(
    r"(?<![a-z])(?:average|avg|mean|median|rate|rates|ratio|ratios|percentage|percent|share|"
    r"growth|change|changes|changed|increase|increased|decrease|decreased|decline|declined|"
    r"trend|trends|proportion|margin|yoy|mom|qoq|per\s+capita|compared|versus|vs)(?![a-z])|"
    r"平均|均值|中位数|比例|占比|比率|增长|增速|同比|环比|变化|趋势|增幅|降幅|对比|相比|率",
    re.IGNORECASE,
)
_RANKING = re.compile(
    r"(?<![a-z])(?:highest|lowest|largest|smallest|biggest|most|least|top|bottom|best|worst|"
    r"maximum|minimum|max|min|rank|ranking)(?![a-z])|最高|最低|最多|最少|最大|最小|排名|前几",
    re.IGNORECASE,
)
_QUALIFIED = re.compile(
    r"#\s+(?:(?:that|which)\s+)?(?:(?:were|was|got|have\s+been|has\s+been|had\s+been|are|is|"
    r"been)\s+)?(?P<verb>[a-z]+(?:ed|en))(?![a-z])",
    re.IGNORECASE,
)
_MEASURE_AFTER = re.compile(
    r"#\s*(?P<noun>amounts?|values?|revenues?|costs?|expenses?|prices?|turnover|days|weight|"
    r"金额|价值|成本|费用|周转|天数|单价)(?![a-z])",
    re.IGNORECASE,
)
_NEUTRAL_EVENTS = frozenset(
    {
        "placed",
        "made",
        "received",
        "completed",
        "opened",
        "created",
        "logged",
        "filed",
        "registered",
        "submitted",
        "raised",
        "recorded",
        "booked",
        "processed",
        "handled",
        "generated",
        "collected",
        "shipped",
        "sold",
        "invoiced",
        "paid",
        "issued",
        "added",
        "acquired",
        "signed",
        "joined",
        "onboarded",
        "reported",
        "delivered",
        "dispatched",
        "seen",
        "earned",
        "taken",
        "gotten",
        "incurred",
        "spent",
    }
)
_CN_CONDITION = re.compile(r"(?:各个|各|按照|按|每个|每|在|来自)\s*(?P<word>[一-鿿]{1,6})")
_CN_NEUTRAL = re.compile(r"^(?:是|有|为|的|一共|总共|合计|多少|共)")
_CAPITAL = re.compile(r"(?<![A-Za-z0-9#'\u2019_-])[A-Z][A-Za-z0-9'\u2019-]*")
_FUNCTION_WORDS = frozenset(
    {
        "what",
        "what's",
        "whats",
        "how",
        "how's",
        "which",
        "show",
        "give",
        "tell",
        "list",
        "display",
        "get",
        "find",
        "please",
        "can",
        "could",
        "would",
        "will",
        "is",
        "are",
        "was",
        "were",
        "do",
        "does",
        "did",
        "has",
        "have",
        "had",
        "total",
        "overall",
        "our",
        "the",
        "a",
        "an",
        "in",
        "for",
        "during",
        "i",
        "i'd",
        "i'm",
        "me",
        "my",
        "we",
        "we've",
        "compute",
        "calculate",
        "return",
        "report",
        "sum",
        "provide",
        "let",
        "need",
        "want",
        "and",
        "of",
        "to",
        "all",
        "so",
        "then",
        "also",
        "hi",
        "hello",
        "now",
        "rmb",
        "cny",
    }
)


def leftover_fragments(
    question: str,
    consumed: list[tuple[int, int]],
    time_spans: tuple[tuple[int, int], ...] = (),
) -> Leftovers:
    """Mask consumed spans, then report remaining temporal and conditional fragments.

    Args:
        question: The original question text.
        consumed: Spans understood by the metric, time and dimension parsers.
        time_spans: The subset of consumed spans that the time parser resolved, used to
            find modifiers such as ``around`` or 之前 that would change the interval.

    Returns:
        The unconsumed time, condition, calculation and ranking fragments.
    """
    masked = list(question)
    for start, end in consumed:
        masked[start:end] = _MASK * (end - start)
    text = "".join(masked)
    times = [hit.group().strip() for hit in TIME_LIKE.finditer(text)]
    times.extend(hit.group() for hit in CAPITAL_MAY.finditer(text))
    times.extend(hit.group() for hit in _TIME_PREPOSITION.finditer(text))
    times.extend(_time_modifiers(text, time_spans))
    conditions = [*_english_conditions(text), *_chinese_conditions(text)]
    conditions.extend(hit.group() for hit in _NUMBER.finditer(text))
    conditions.extend(
        hit.group().lstrip(_MASK).strip()
        for hit in _QUALIFIED.finditer(text)
        if hit.group("verb").casefold() not in _NEUTRAL_EVENTS
    )
    conditions.extend(hit.group("noun") for hit in _MEASURE_AFTER.finditer(text))
    return Leftovers(
        times=tuple(dict.fromkeys(times)),
        conditions=tuple(dict.fromkeys(item for item in conditions if item not in times)),
        calculations=tuple(dict.fromkeys(hit.group() for hit in _CALCULATION.finditer(text))),
        rankings=tuple(dict.fromkeys(hit.group() for hit in _RANKING.finditer(text))),
    )


def _folded(word: str) -> str:
    """Compare words case-insensitively with typographic apostrophes read as ASCII ones."""
    return word.casefold().replace("\u2019", "'")


def _english_conditions(text: str) -> list[str]:
    found = [
        hit.group()
        for hit in _EN_CONDITION.finditer(text)
        if _folded(hit.group("word")) not in _NEUTRAL
        and _folded(hit.group("word")).removesuffix("'s") not in _NEUTRAL
    ]
    found.extend(
        hit.group()
        for hit in _CAPITAL.finditer(text)
        if _folded(hit.group()) not in _FUNCTION_WORDS and hit.group() != "May"
    )
    return found


def _chinese_conditions(text: str) -> list[str]:
    return [
        hit.group()
        for hit in _CN_CONDITION.finditer(text)
        if not _CN_NEUTRAL.match(hit.group("word"))
    ]


def _time_modifiers(text: str, spans: tuple[tuple[int, int], ...]) -> list[str]:
    found: list[str] = []
    for start, end in spans:
        before = _MODIFIER_BEFORE.search(text[:start])
        after = _MODIFIER_AFTER.match(text[end:])
        found.extend(hit.group().strip() for hit in (before, after) if hit is not None)
    return found
