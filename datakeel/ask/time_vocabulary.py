# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual calendar vocabulary shared by the time parser and the consumption guard."""

import re

MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
ORDINALS: dict[str, int] = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
}
NUMBER_WORDS: dict[str, int] = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "a": 1,
    "an": 1,
}
CHINESE_NUMBERS: dict[str, int] = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "十一": 11,
    "十二": 12,
}

YEAR = r"(?<![0-9A-Za-z])(?P<year>(?:19|20)\d{2})(?![0-9])"
MONTH = (
    r"(?<![a-z])(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
    r"aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?(?![a-z])"
)
ORDINAL = r"(?P<ord>first|second|third|fourth|1st|2nd|3rd|4th)"
CN_MONTH = r"(?P<mm>\d{1,2}|十[一二]?|[一二三四五六七八九])"
CN_QUARTER = r"(?P<q>[1-4一二三四])"
COUNT = r"(?P<n>\d{1,5}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|a|an)"
CN_COUNT = r"(?P<n>\d{1,5}|十[一二]?|[一二两三四五六七八九十])"

# Anchors that turn a neighboring period into a boundary, a range or an open interval.
AS_OF_PREFIX = re.compile(
    r"(?:(?<![a-z])(?:(?:(?:as\s+(?:of|at)|at|by|to|until|till|through|up\s+to)\s+)?"
    r"(?:the\s+)?end\s+of|as\s+(?:of|at)|through|thru|up\s+(?:to|until|till)|until|till)"
    r"\s+(?:the\s+)?|(?:累计)?(?:截至|截止(?:到|至)?|直到|到|至)\s*)$",
    re.IGNORECASE,
)
AS_OF_SUFFIX = re.compile(r"^(?:\s*(?:底|末)|[- ]end\b)", re.IGNORECASE)
SINCE_PREFIX = re.compile(
    r"(?:\b(?:since|starting(?:\s+(?:from|in))?|beginning(?:\s+(?:from|in))?)\s+(?:the\s+)?|"
    r"自\s*)$",
    re.IGNORECASE,
)
SINCE_SUFFIX = re.compile(r"^\s*(?:以来|至今|起|开始|onwards?\b|to\s+date\b)", re.IGNORECASE)
RANGE_OPEN = re.compile(r"(?:\b(?:from|between)\s+(?:the\s+)?|(?:从|自)\s*)$", re.IGNORECASE)
RANGE_JOIN = re.compile(
    r"^\s*(?:to|through|thru|until|till|and|-|\u2013|\u2014|~|\uff5e|到|至)\s*(?:the\s+)?$",
    re.IGNORECASE,
)
LEAD = re.compile(
    r"(?:\b(?:in|for|during|over|within|throughout|of|on|across|at)\s+"
    r"(?:the\s+(?:(?:calendar\s+)?(?:month|quarter|year|period)\s+of\s+)?)?|在\s*)$",
    re.IGNORECASE,
)
POSSESSIVE = re.compile(r"^(?:['\u2019]s\b)", re.IGNORECASE)

# Words that still look temporal after every recognized expression has been removed.
_EN_TIME_WORDS = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|june?|july?|aug(?:ust)?|"
    r"sept?(?:ember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?|quarters?|quarterly|q\d+|"
    r"h\d|half|halves|years?|yearly|annual(?:ly)?|months?|monthly|weeks?|weekly|days?|daily|"
    r"today|yesterday|tomorrow|tonight|ytd|mtd|qtd|wtd|fy\d*|fiscal|since|until|till|"
    r"recently|latest|weekends?|weekdays?|holidays?|fortnights?|seasons?|seasonal|peak|off-peak|"
    r"mornings?|evenings?|nights?|overnight|hours?|hourly|noon|midnight|semesters?|decades?|"
    r"christmas|easter|black\s+friday|lunar"
)
TIME_LIKE = re.compile(
    rf"(?<![a-z0-9])(?:{_EN_TIME_WORDS})(?![a-z0-9])|"
    r"(?<![a-z])(?:last|this|previous|prior|past|current|next|coming|recent|early|late|mid)"
    r"(?=[\s-]+(?:[a-z0-9]|#))|"
    r"\b(?:as\s+(?:of|at)|end\s+of|beginning\s+of|start\s+of)\b|"
    r"(?<![0-9])(?:19|20)\d{2}(?![0-9])|"
    r"\d+\s*(?:年|月|季|周|天|日|号)|[一二两三四五六七八九十]+\s*(?:月|季)|"
    r"(?:上|本|这|下|当|今|去|明|前)\s*(?:个|一)?\s*(?:年|月|季|周|星期|天)|"
    r"截至|截止|以来|至今|月底|月末|年底|年末|季末|年初|月初|期末|期初|最近|近期|过去|未来|"
    r"上半年|下半年|年度|季度|全年|财年|财季|会计年度|学年|农历|春节|国庆|元旦|节假日|假期|节日|"
    r"旺季|淡季|周末|工作日|上旬|中旬|下旬|月中|年中|季中|半月|双十一|双11|夜间|白天|早上|晚上|凌晨",
    re.IGNORECASE,
)
CAPITAL_MAY = re.compile(r"(?<![A-Za-z])May(?![A-Za-z])")
