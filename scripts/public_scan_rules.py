# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check public text, preserving exact line locations and narrowly masking valid lock hashes."""

from __future__ import annotations

import ast
import base64
import binascii
import fnmatch
import ipaddress
import json
import re
import tomllib

from scripts.public_scan_models import LineFinding

_EMAIL = re.compile(r"\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_LOCAL = re.compile(r"/" + r"(?:Users/|home/[^/\s'\"<>]+)")
_INTERNAL = re.compile(
    r"\b(?:" + "|".join(("solar" + "sense", "qa" + "pex", "j" + "lw", "cloud" + "main")) + r")\b",
    re.IGNORECASE,
)
_MESSAGE = re.compile(
    "|".join(
        (
            "co" + "dex",
            "clau" + "de",
            "ki" + "mi",
            "SPEC" + "-P",
            "验收" + "记录",
            "修" + "订单",
            "任务" + "包",
            "pro" + "mpt",
        )
    ),
    re.IGNORECASE,
)
_IP = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.])")
_PRIVATE_NETWORKS = (
    ipaddress.IPv4Network((10 << 24, 8)),
    ipaddress.IPv4Network(((172 << 24) | (16 << 16), 12)),
    ipaddress.IPv4Network(((192 << 24) | (168 << 16), 16)),
)
_SECRETS = (
    re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])"),
    re.compile(r"(?<![\w-])sk-[-A-Za-z0-9_]{16,}"),
    re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY-----"),
)
_ASSIGNMENT = re.compile(
    r"\b(?:password|token)\s*=(?!=)\s*(?:[\"'][^\"'\s]+|[^=\s\"',;&)]+)", re.IGNORECASE
)
_JSON_HASH = re.compile(r'"integrity"\s*:\s*"(?P<value>(?:\\.|[^"\\])*)"')
_TOML_HASH = re.compile(r'\bhash\s*=\s*"(?P<value>[^"\n]*)"')


def noreply_email(value: str) -> bool:
    """Accept only a complete address under the public GitHub contributor identity domain."""
    return bool(_EMAIL.fullmatch(value)) and value.lower().endswith("@users.noreply.github.com")


def reserved_email(value: str) -> bool:
    """Accept reserved example domains and their descendants without weakening identity rules."""
    if not _EMAIL.fullmatch(value):
        return False
    domain = value.rsplit("@", 1)[1].lower()
    examples = ("example.com", "example.org", "example.net")
    suffixes = (".example", ".invalid", ".test", ".localhost")
    return domain in examples or domain.endswith(
        (*tuple("." + name for name in examples), *suffixes)
    )


def _valid_hash(value: str, *, integrity: bool) -> bool:
    separator = "-" if integrity else ":"
    algorithm, found, encoded = value.partition(separator)
    sizes = {"sha256": 32, "sha384": 48, "sha512": 64}
    if not found or algorithm not in sizes:
        return False
    try:
        decoded = base64.b64decode(encoded, validate=True) if integrity else bytes.fromhex(encoded)
    except (binascii.Error, ValueError):
        return False
    return len(decoded) == sizes[algorithm]


def _mask_hashes(path: str, text: str) -> str:
    name = path.rsplit("/", 1)[-1]
    try:
        if name == "package-lock.json":
            json.loads(text)
            pattern, integrity = _JSON_HASH, True
        elif name == "uv.lock":
            tomllib.loads(text)
            pattern, integrity = _TOML_HASH, False
        else:
            return text
    except (json.JSONDecodeError, tomllib.TOMLDecodeError):
        return text
    characters = list(text)
    for match in pattern.finditer(text):
        value = json.loads('"' + match.group("value") + '"') if integrity else match.group("value")
        if isinstance(value, str) and _valid_hash(value, integrity=integrity):
            start, end = match.span("value")
            characters[start:end] = " " * (end - start)
    return "".join(characters)


def excluded_path(path: str, patterns: tuple[str, ...]) -> bool:
    """Match excluded file paths; directory exclusions cover every descendant."""
    return any(
        path.startswith(pattern) if pattern.endswith("/") else fnmatch.fnmatchcase(path, pattern)
        for pattern in patterns
    )


def _excluded_references(text: str, patterns: tuple[str, ...]) -> tuple[int, ...]:
    lines: set[int] = set()
    for pattern in patterns:
        if "/" not in pattern:
            continue
        reference = pattern.removesuffix("/")
        expression = re.escape(reference).replace(r"\*", r"[^\s`\"'<>)]*").replace(r"\?", r"[^\s]")
        if pattern.endswith("/"):
            expression += r"(?=/|$|[\s`\"'<>),])"
        for match in re.finditer(expression, text):
            lines.add(text.count("\n", 0, match.start()) + 1)
    return tuple(sorted(lines))


def _private_ip(value: str) -> bool:
    try:
        address = ipaddress.IPv4Address(value)
    except ipaddress.AddressValueError:
        return False
    return any(address in network for network in _PRIVATE_NETWORKS)


def _nonliteral(value: ast.expr) -> bool:
    return not any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, (str, bytes, int, float, complex))
        and (not isinstance(node.value, (str, bytes)) or bool(node.value))
        for node in ast.walk(value)
    )


def _assignments(tree: ast.AST) -> tuple[ast.AST, ...]:
    result: list[ast.AST] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.keyword)
            and node.arg in {"token", "password"}
            and _nonliteral(node.value)
        ):
            result.append(node)
        elif (
            isinstance(node, (ast.Assign, ast.AnnAssign))
            and node.value is not None
            and _nonliteral(node.value)
        ):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                isinstance(target, (ast.Name, ast.Attribute))
                and (target.id if isinstance(target, ast.Name) else target.attr)
                in {"token", "password"}
                for target in targets
            ):
                result.append(node)
    return tuple(result)


def _credential_source(path: str, source: str) -> str:
    if not path.endswith(".py"):
        return source
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return source
    lines = source.splitlines(keepends=True)
    characters = list(source)
    for node in _assignments(tree):
        segment = ast.get_source_segment(source, node)
        if segment is None or not isinstance(node, (ast.keyword, ast.Assign, ast.AnnAssign)):
            continue
        start = sum(map(len, lines[: node.lineno - 1])) + len(
            lines[node.lineno - 1].encode()[: node.col_offset].decode()
        )
        match = _ASSIGNMENT.search(segment)
        if match is not None:
            position = start + segment.index("=", match.start())
            characters[position] = " "
    return "".join(characters)


def text_findings(
    path: str, text: str, patterns: tuple[str, ...], *, message: bool = False
) -> tuple[LineFinding, ...]:
    """Scan text and references; log globs apply only to paths, Python expressions are not keys."""
    source = _mask_hashes(path, text)
    found: set[tuple[int, str]] = set()
    rules = [("local_path", _LOCAL), ("internal_name", _INTERNAL)]
    rules.extend(("secret", expression) for expression in _SECRETS)
    credential_source = _credential_source(path, source)
    found.update(
        (source.count("\n", 0, match.start()) + 1, "secret")
        for match in _ASSIGNMENT.finditer(credential_source)
    )
    if message:
        rules.append(("commit_message", _MESSAGE))
    for rule, expression in rules:
        found.update(
            (source.count("\n", 0, match.start()) + 1, rule)
            for match in expression.finditer(source)
        )
    found.update(
        (source.count("\n", 0, match.start()) + 1, "email")
        for match in _EMAIL.finditer(source)
        if not noreply_email(match.group()) and not reserved_email(match.group())
    )
    found.update(
        (source.count("\n", 0, match.start()) + 1, "private_ip")
        for match in _IP.finditer(source)
        if _private_ip(match.group())
    )
    found.update((line, "excluded_path") for line in _excluded_references(source, patterns))
    return tuple(LineFinding(line=line, rule=rule) for line, rule in sorted(found))
