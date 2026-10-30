# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compiled bounded candidate patterns for the shared offline privacy detector."""

import re

# Necessary substrings only: these filters never establish a privacy finding.
NUMBER_RUN = re.compile(r"[0-9][0-9 ()-]{6}")
ASCII_LETTER = re.compile(r"[A-Za-z]")
SECRET_HINT = re.compile(r"sk-|AKIA|ASIA|gh[pousr]_|github_pat_|xox[baprs]-|AIza|eyJ")
LABEL_HINT = re.compile(
    r"api|access|auth|secret|aws|client|github|gh|password|passwd|pwd|token|bearer|key|pass|"
    r"密码|口令|密钥|令牌",
    re.IGNORECASE,
)

EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}(?![A-Za-z0-9_-])"
)
PHONE = re.compile(
    r"(?<![A-Za-z0-9_./\d$¥€£\uffe5-])(?!(?:\d{4}[-/]\d{2}[-/]\d{2})(?!\d))"
    r"\+?(?:[0-9][ ()-]*){7,14}[0-9](?![A-Za-z0-9_\d]|[ ()-]*[0-9]|\.[0-9]|%|元)"
)
CHINA_MOBILE = re.compile(
    r"(?<![A-Za-z0-9_.\d$¥€£\uffe5])(?:(?:\+|00)?86[ -]*)?1[3-9](?:[ -]?[0-9]){9}"
    r"(?![A-Za-z0-9_\d]|\.[0-9]|%|元)"
)
CHINA_PHONE_DIGITS = re.compile(r"(?:86)?1[3-9][0-9]{9}\Z")
LOCAL_PHONE = re.compile(
    r"(?:0[1-9][0-9]{1,2}[ -]+[0-9]{3,4}[ -]?[0-9]{4}"
    r"|[2-9][0-9]{2}[ -][0-9]{3}[ -][0-9]{4})\Z"
)
# A bracketed area code is mainland evidence only when it starts with 0 or is +86.
PARENTHESIZED_PHONE = re.compile(
    r"(?<![A-Za-z0-9_./\d$¥€£\uffe5-])"
    r"(?:(?:\(0[1-9][0-9]{1,2}\)|\uff080[1-9][0-9]{1,2}\uff09)"
    r"[ -]*[0-9]{3,4}[ -]?[0-9]{4}"
    r"|(?:\(\+86\)|\uff08\+86\uff09)[ -]*"
    r"(?:1[3-9](?:[ -]?[0-9]){9}|0?[1-9][0-9]{1,2}[ -]*[0-9]{3,4}[ -]?[0-9]{4}))"
    r"(?![A-Za-z0-9_\d]|[ ()\uff08\uff09-]*[0-9]|\.[0-9]|%|元)"
)
_SEQUENCED_PHONE = (
    r"0[1-9][0-9]{1,2}-[0-9]{7,8}"
    r"|(?:\(|\uff08)0[1-9][0-9]{1,2}(?:\)|\uff09)[ -]?[0-9]{7,8}"
    r"|(?:\+86[ -]?)?1[3-9][0-9]{9}"
)
# Complete phones separated by exactly one space are independent findings.
PHONE_SEQUENCE = re.compile(
    r"(?<![A-Za-z0-9_./\d$¥€£\uffe5-])"
    r"(?:" + _SEQUENCED_PHONE + r")(?: (?:" + _SEQUENCED_PHONE + r"))+"
    r"(?![A-Za-z0-9_\d]|[ ()\uff08\uff09-]*[0-9]|\.[0-9]|%|元)"
)
SEQUENCED_PHONE = re.compile(_SEQUENCED_PHONE)
# Reference numbers: an identifier word immediately before, or 号 immediately after.
PHONE_REFERENCE_BEFORE = re.compile(
    r"(?:编号|单号|批次号?|批号|序号|流水号|合同号|发票号|案号|文号|"
    r"(?<![A-Za-z])(?:(?:No|Nr|Ref)\.|(?:Order|Invoice|Batch|Serial|Ticket)\b)|[#\uff03\u2116])"
    r"[ \t:\uff1a#\uff03.]{0,3}\Z",
    re.IGNORECASE,
)
# "Tel No." and similar keep their phone meaning.
PHONE_LABEL_BEFORE_REFERENCE = re.compile(
    r"(?:tel|telephone|phone|mobile|cell|fax|contact|电话|手机)[ \t.]*\Z", re.IGNORECASE
)
PHONE_REFERENCE_AFTER = "号"
CHINA_ID = re.compile(r"(?<![A-Za-z0-9_])[1-9][0-9]{16}[0-9Xx](?![A-Za-z0-9_])")
BANK_CARD = re.compile(r"(?<![A-Za-z0-9_+])[1-9](?:[ -]?[0-9]){12,18}(?![A-Za-z0-9_]|[ -]*[0-9])")
IPV4 = re.compile(r"(?<![A-Za-z0-9_.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![A-Za-z0-9_.])")
IPV6 = re.compile(
    r"(?<![A-Za-z0-9_.:])(?:[0-9A-Fa-f]{0,4}:){2,7}"
    r"(?:[0-9A-Fa-f]{0,4}|(?:[0-9]{1,3}\.){3}[0-9]{1,3})(?![A-Za-z0-9_.:])"
)
LABELED_IP = re.compile(
    r"(?<![\w:])[^\W\d][\w-]{0,63}\s*:\s*"
    r"(?P<value>[0-9A-Fa-f:][A-Za-z0-9_.:%-]*)(?![A-Za-z0-9_.:%-])"
)
# Shared prose punctuation ends bare credentials and the host/path of credential URLs.
# Userinfo and quoted values retain their own boundaries so their contents stay covered.
CREDENTIAL_PROSE_STOPS = (
    r"\uff0c。\uff1b\uff01\uff1f\uff1a「」《》、【】“”\u2018\u2019"
    r"\uff08\uff09\u2026\u2014"
    r"\uff5e\u00b7\uff5c\u3009\u300f\u3015\u3017"
)
CREDENTIAL_URL = re.compile(
    r"(?<![A-Za-z0-9_+.-])[A-Za-z][A-Za-z0-9+.-]{1,20}://"
    r"[^\s/@]+@"
    r"(?:\[[0-9A-Fa-f:.]+\]|[^\s<>\[\](){}\"'`"
    + CREDENTIAL_PROSE_STOPS
    + r"\u2e80-\ua4cf\uac00-\ud7af\uf900-\ufaff\ufe10-\ufe6f\uff00-\uffef\U00020000-\U000323af])*"
)
SECRET = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{16,}"
    r"|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AIza[A-Za-z0-9_-]{30,}"
    r"|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"
    r")(?![A-Za-z0-9_])"
)
_ASCII_CREDENTIAL_LABELS = (
    r"api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"(?:aws[_-]?)?secret[_-]?(?:access[_-]?)?key|client[_-]?secret|"
    r"(?:github|gh)[_-]?token|password|passwd|pwd|secret|token"
)
# Environment/config keys: bounded `_`, `-` or `.` segments before a credential word.
_PREFIXED_CREDENTIAL_LABEL = (
    r"(?:[A-Za-z0-9]{1,32}[_.-]){1,8}(?:"
    + _ASCII_CREDENTIAL_LABELS
    + r"|pass(?:phrase)?|private[_-]?key)"
)
CREDENTIAL_LABEL_PATTERN = (
    r"(?:(?<![A-Za-z0-9_])|(?=[\u3400-\u9fff]))(?P<label>"
    + _PREFIXED_CREDENTIAL_LABEL
    + r"|"
    + _ASCII_CREDENTIAL_LABELS
    + r"|key|auth|"
    r"访问密钥|访问令牌|密码|口令|密钥|令牌)"
)
CREDENTIAL_SEPARATOR = r"[\"']?\s*(?:[:=\uff1a]|[是为]\s*[:\uff1a]?)\s*"
CREDENTIAL_ASSIGNMENT = re.compile(CREDENTIAL_LABEL_PATTERN + CREDENTIAL_SEPARATOR, re.IGNORECASE)
CREDENTIAL_VALUE_START = (
    r"(?!" + CREDENTIAL_LABEL_PATTERN.replace("(?P<label>", "(?:") + CREDENTIAL_SEPARATOR + r")"
)
# Stop bare values before surrounding prose; quotes permit spaces and escaped punctuation.
BARE_CREDENTIAL_PATTERN = r"[^\s\"'<>,;" + CREDENTIAL_PROSE_STOPS + r"\u3400-\u9fff]+"
LABELED_SECRET = re.compile(
    CREDENTIAL_LABEL_PATTERN
    + CREDENTIAL_SEPARATOR
    + CREDENTIAL_VALUE_START
    + rf"(?P<value>{BARE_CREDENTIAL_PATTERN})",
    re.IGNORECASE,
)
QUOTED_SECRET = re.compile(
    CREDENTIAL_LABEL_PATTERN
    + CREDENTIAL_SEPARATOR
    + r"""(?P<quote>["'])(?P<value>(?:\\.|[^\\])*?)(?P=quote)""",
    re.IGNORECASE,
)
BEARER = re.compile(r"(?<![A-Za-z0-9_])Bearer\s+(?P<value>[A-Za-z0-9._~+/-]{16,}=*)", re.IGNORECASE)
PRIVATE_KEY = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    r"[\sA-Za-z0-9+/=]+-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
SECRET_VALUE = re.compile(r"\S{8,}\Z")
