# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Grammatical cues that bind registered dimension words to grouping or filtering roles."""

import re

_I = re.IGNORECASE
_EN = r"(?<![a-z])"

GROUP_BEFORE = re.compile(
    rf"(?:{_EN}(?:by|per|for\s+(?:each|every)|each|every|across(?:\s+(?:all|the|each))?|"
    r"(?:broken|break(?:\s+(?:it|this|that|them))?|breaking)\s+(?:down|out)\s+by|"
    r"break\s*down\s+by|breakdown\s+(?:by|of)|split\s+(?:out\s+)?by|grouped\s+by|group\s+by|"
    r"segmented\s+by|which|what)\s+(?:the\s+|each\s+|every\s+|all\s+)?|"
    r"(?:各个|各|按照|按|分|每个|每|哪个|哪些|哪一个|哪)\s*)$",
    _I,
)
GROUP_AFTER = re.compile(
    r"^(?:['\u2019]s\s+breakdown|\s*-?\s*wise\b|\s+breakdown\b|\s+split\b|\s+distribution\b|"
    r"\s*(?:分布|拆分|明细|分组|分别))",
    _I,
)
FILTER_BEFORE = re.compile(
    rf"(?:{_EN}(?:in|for|from|at|within|inside|among|of|on|via|through)\s+"
    r"(?:the\s+|our\s+|its\s+)?|在\s*|(?:来自|通过)\s*)$",
    _I,
)
NEGATION_BEFORE = re.compile(
    rf"(?:{_EN}(?:excluding|exclude|except(?:\s+for)?|other\s+than|outside(?:\s+(?:of|the))?|"
    r"not\s+(?:in|including|from|counting)|without|apart\s+from|besides|minus|non)\s*-?\s*"
    r"(?:the\s+)?|(?:除了|除|不含|不包括|除去|剔除|排除|扣除|非)\s*)$",
    _I,
)
NEGATION_AFTER = re.compile(r"^\s*(?:以外|之外|除外)")
NAME_VALUE_GAP = re.compile(r"^\s*(?:of|:|\uff1a|为|是|的|=)?\s*$", _I)
VALUE_GROUP_BEFORE = re.compile(
    rf"(?:{_EN}(?:each|every|per|by|for\s+(?:each|every))\s+(?:the\s+)?|(?:各个|各|每个|每)\s*)$",
    _I,
)
# Words that may directly follow an English value alias without forming a longer noun phrase.
VALUE_FOLLOWER = re.compile(
    r"^(?:\s*$|\s*[^\w\s]|\s+(?:and|or|but|vs|versus|in|for|from|at|on|during|over|with|by|"
    r"to|of|as|than|since|until|through|last|this|next|previous|prior|past|current|first|second|"
    r"third|fourth|1st|2nd|3rd|4th|was|were|is|are|did|had|has|have|only|alone|please|"
    r"year|years|month|months|quarter|quarters|week|weeks|ytd|mtd|qtd|today|yesterday|"
    r"q[1-4]|h[12]|\d|jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec|january|february|"
    r"march|april|june|july|august|september|october|november|december)(?![a-z]))",
    _I,
)
