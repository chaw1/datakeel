# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Compiled bounded candidate patterns for the shared offline privacy detector."""

import re

# Necessary substrings only: these filters never establish a privacy finding.
NUMBER_RUN = re.compile(r"[0-9][0-9 ()-]{6}")
ASCII_LETTER = re.compile(r"[A-Za-z]")
SECRET_HINT = re.compile(r"sk-|AKIA|ASIA|gh[pousr]_|github_pat_|xox[baprs]-|AIza|eyJ")
LABEL_HINT = re.compile(
    r"api|access|auth|secret|aws|client|github|gh|password|passwd|pwd|token|bearer|"
    r"密码|口令|密钥|令牌",
    re.IGNORECASE,
)

EMAIL = re.compile(
    r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9_%+-]+(?:\.[A-Za-z0-9_%+-]+)*@"
    r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
    r"[A-Za-z]{2,63}(?![A-Za-z0-9_-])"
)
PHONE = re.compile(
    r"(?<![A-Za-z0-9_/-])(?!(?:\d{4}[-/]\d{2}[-/]\d{2})(?!\d))"
    r"\+?(?:[0-9][ ()-]*){7,14}[0-9](?![A-Za-z0-9_]|[ ()-]*[0-9])"
)
CHINA_MOBILE = re.compile(r"(?<![A-Za-z0-9_])(?:(?:\+|00)?86[ -]?)?1[3-9][0-9]{9}(?![A-Za-z0-9_])")
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
CREDENTIAL_URL = re.compile(
    r"(?<![A-Za-z0-9_+.-])[A-Za-z][A-Za-z0-9+.-]{1,20}://"
    r"[^\s/@]+@"
    r"(?:\[[0-9A-Fa-f:.]+\]|[^\s<>\[\](){}\"'`\uff0c。\uff1b\uff01\uff1f\uff1a\uff08\uff09【】“”\u2018\u2019])+"
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
CREDENTIAL_LABEL_PATTERN = (
    r"(?:(?<![A-Za-z0-9_])|(?=[\u3400-\u9fff]))(?P<label>api[_-]?key|access[_-]?token|auth[_-]?token|"
    r"(?:aws[_-]?)?secret[_-]?(?:access[_-]?)?key|client[_-]?secret|"
    r"(?:github|gh)[_-]?token|password|passwd|pwd|secret|token|"
    r"访问密钥|访问令牌|密码|口令|密钥|令牌)"
)
CREDENTIAL_SEPARATOR = r"[\"']?\s*[:=\uff1a是为]\s*"
CREDENTIAL_ASSIGNMENT = re.compile(CREDENTIAL_LABEL_PATTERN + CREDENTIAL_SEPARATOR, re.IGNORECASE)
CREDENTIAL_VALUE_START = (
    r"(?!" + CREDENTIAL_LABEL_PATTERN.replace("(?P<label>", "(?:") + CREDENTIAL_SEPARATOR + r")"
)
# Stop bare values before surrounding prose; quotes permit spaces and escaped punctuation.
BARE_CREDENTIAL_PATTERN = (
    r"[^\s\"'<>,;\uff0c。\uff1b\uff01\uff1f\uff1a「」《》、【】“”\u2018\u2019\u3400-\u9fff]{8,}"
)
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
