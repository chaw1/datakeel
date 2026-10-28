# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Require whole literal identities in explicit naming and ownership contexts."""

import json
import re
import unicodedata

from pydantic import JsonValue

from datakeel.core.datasheet_models import DatasheetFact
from datakeel.datasheets.number_words import erase_written_numbers, written_numbers
from datakeel.datasheets.vocabulary import KIND_LABELS

_QUOTED = re.compile(
    r'"((?:\\.|[^"\\\n])+)"|“([^”\n]+)”|「([^」\n]+)」|『([^』\n]+)』|\u2018([^\u2019\n]+)\u2019'
)
_END = r"[^。\uff01\uff1f!?\uff1b;\n]+"
_ENGLISH_ROLES = "owner|maintainer|creator|reviewer|company|organization|organisation|team"
_CHINESE_ROLES = "负责人|维护人|创建人|审阅人|所有者|机构|组织|团队|公司|发布方|分发方"
_ROLE_PATTERNS = (
    re.compile(
        r"\b(?:dataset name|name|"
        + _ENGLISH_ROLES
        + r")\s*(?:is|was|called|named|:|=)\s*("
        + _END
        + ")",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:owned|maintained|created|collected|provided|published|managed|reviewed)\s+by\s+("
        + _END
        + ")",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:named|called)\s+(" + _END + ")", re.IGNORECASE),
    re.compile(
        r"\b(?:" + _ENGLISH_ROLES + r")\s+(?!is\b|was\b|has\b|contains\b)(" + _END + ")",
        re.IGNORECASE,
    ),
    # Passive clauses ("was created on") have no actor before the verb; "by" phrases cover them.
    re.compile(
        r"^(.*?)(?<!\bwas)(?<!\bwere)(?<!\bis)(?<!\bare)(?<!\bbeen)(?<!\bbe)"
        r"\s+(?:owns|maintains|manages|created|collected|reviews)\b",
        re.IGNORECASE,
    ),
    re.compile(r"^(.*?)\s+is\s+(?:the\s+)?(?:" + _ENGLISH_ROLES + r")\b", re.IGNORECASE),
    re.compile(
        r"(?:名称|名字|" + _CHINESE_ROLES + r")(?:是|为|叫做|叫|名为|[:\uff1a])\s*(" + _END + ")"
    ),
    re.compile(r"由(.+?)(?:负责)?(?:维护|创建|采集|收集|提供|分发|管理|发布)"),
    # 「负责人」 is the role noun, not the verb 「负责」; its value is checked by the role pattern.
    re.compile(
        r"^(.+?)(?:负责(?!人)(?:维护|创建|采集|收集|审阅)?|(?:是|为)(?:" + _CHINESE_ROLES + "))"
    ),
    re.compile(r"^(.+?)(?:负责)?(?:创建|维护|管理|提供)(?:了)?(?:该|本)?数据集"),
)
_NAME_MARKER = re.compile(
    r"\s*[(\uff08]\s*(?:" + "|".join(KIND_LABELS["name"]) + r")\s*[)\uff09]\s*\.?\s*$",
    re.IGNORECASE,
)
_NUMERAL_ONLY = re.compile(r"[\d零\u3007一二两三四五六七八九十百千万亿]+")


def _strings(value: JsonValue) -> tuple[str, ...]:
    if isinstance(value, dict):
        return tuple(value) + tuple(part for item in value.values() for part in _strings(item))
    if isinstance(value, list):
        return tuple(part for item in value for part in _strings(item))
    return (value,) if isinstance(value, str) else ()


def _fold(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _literal_supported(candidate: str, values: tuple[str, ...]) -> bool:
    candidate = _fold(candidate.strip(" \t\r\n\"'“”\u2018\u2019「」『』.,\uff0c\uff1a:"))
    if not candidate:
        return False
    if _NUMERAL_ONLY.fullmatch(candidate):
        return candidate in values
    if re.search(r"[a-z]", candidate):
        pattern = re.compile(r"(?<!\w)" + re.escape(candidate) + r"(?!\w)")
        return any(pattern.search(value) for value in values)
    return any(candidate in value for value in values)


def _name_supported(candidate: str, values: tuple[str, ...], structured: tuple[str, ...]) -> bool:
    # The prompt marks names as "(name)"; copying that marker does not change the identity.
    candidate = _NAME_MARKER.sub("", candidate)
    if _fold(candidate.rstrip(".")) in structured:
        return True
    candidate = (
        re.split(
            r"\s+(?:and|which|who|that)\s+(?:has|contains|is|was|are|includes)\b|[\uff0c,]|(?:并且|并由)",
            candidate,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]
        .strip()
        .rstrip(".")
    )
    if _literal_supported(candidate, values):
        return True
    names = re.split(r"\s+(?:and|or)\s+|[、]|和|及|与", candidate, flags=re.IGNORECASE)
    return len(names) > 1 and all(_literal_supported(name, values) for name in names)


def _quoted_value(match: re.Match[str]) -> str | None:
    if match.group(1) is None:
        return next(part for part in match.groups() if part is not None)
    try:
        value: JsonValue = json.loads(match.group())
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, str) else None


def names_supported(text: str, facts: tuple[DatasheetFact, ...]) -> bool:
    """Reject invented identities even when their words resemble grammar or cardinal numbers."""
    values = tuple(_fold(part) for fact in facts for part in _strings(fact.value))
    structured = tuple(
        _fold(json.dumps(fact.value, ensure_ascii=False))
        for fact in facts
        if isinstance(fact.value, (list, dict))
    )
    for match in _QUOTED.finditer(text):
        quoted = _quoted_value(match)
        if quoted is None:
            return False
        numeric = _fold(quoted)
        if re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?", numeric):
            continue
        if written_numbers(numeric) and not erase_written_numbers(numeric).strip():
            continue
        if not _literal_supported(quoted, values):
            return False
    return all(
        _name_supported(match.group(1), values, structured)
        for pattern in _ROLE_PATTERNS
        for match in pattern.finditer(text)
    )
