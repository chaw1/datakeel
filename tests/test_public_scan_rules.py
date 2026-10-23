# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated text samples verify history privacy rules without embedding sensitive fixtures."""

from __future__ import annotations

import json

import pytest

from scripts.public_scan_rules import excluded_path, noreply_email, text_findings


def local_path() -> str:
    """Build a synthetic personal path without publishing the detector's own sample."""
    return "/" + "Users" + "/generated"


def address(*octets: int) -> str:
    """Format generated network boundary samples at runtime."""
    return ".".join(map(str, octets))


def email() -> str:
    """Build an undeliverable email only in the test process."""
    return "generated" + "@" + "example.invalid"


def rules(source: str, path: str = "sample.txt") -> set[str]:
    """Collect matched rule identifiers without retrieving source values."""
    return {item.rule for item in text_findings(path, source, ())}


@pytest.mark.parametrize(
    ("value", "rule"),
    [
        (local_path(), "local_path"),
        ("/" + "home" + "/generated/data", "local_path"),
        (email(), "email"),
        ("Solar" + "Sense", "internal_name"),
        ("QA" + "pex", "internal_name"),
        ("J" + "LW", "internal_name"),
        ("CLOUD" + "MAIN", "internal_name"),
        (address(10, 0, 0, 1), "private_ip"),
        (address(172, 16, 0, 1), "private_ip"),
        (address(172, 31, 255, 255), "private_ip"),
        (address(192, 168, 1, 1), "private_ip"),
        ("AK" + "IA" + "A" * 16, "secret"),
        ("s" + "k-" + "a" * 24, "secret"),
        ("-----BEGIN " + "RSA PRIVATE" + " KEY-----", "secret"),
        ("pass" + "word=" + "generated", "secret"),
        ("to" + "ken=" + "generated", "secret"),
    ],
)
def test_sensitive_text_has_exact_line_and_redacted_evidence(value: str, rule: str) -> None:
    """Every required privacy class is detected without copying its value into results."""
    findings = text_findings("sample.txt", "safe\n" + value + "\n", ())
    assert any(item.rule == rule and item.line == 2 for item in findings)
    assert all(value not in item.model_dump_json() for item in findings)


@pytest.mark.parametrize(
    "value",
    [
        "34927473+chaw1@users.noreply.github.com",
        "ask-" + "a" * 24,
        "x" + "solar" + "sense" + "x",
        "j" + "lw" + "package",
        address(127, 0, 0, 1),
        address(172, 15, 255, 255),
        address(172, 32, 0, 0),
        address(192, 169, 0, 1),
        address(8, 8, 8, 8),
        address(10, 999, 0, 1),
        "to" + "ken=",
        "to" + 'ken=""',
    ],
)
def test_safe_boundaries_and_empty_credentials_do_not_match(value: str) -> None:
    """Word boundaries and precise private ranges prevent accidental broad exclusions."""
    assert rules(value) == set()


@pytest.mark.parametrize(
    "word",
    [
        "co" + "dex",
        "clau" + "de",
        "ki" + "mi",
        "SPEC" + "-P",
        "验收" + "记录",
        "修" + "订单",
        "任务" + "包",
        "pro" + "mpt",
    ],
)
def test_commit_only_terms_are_case_insensitive(word: str) -> None:
    """Process vocabulary is forbidden in messages without banning legitimate source identifiers."""
    assert rules(word) == set()
    assert text_findings("", "safe\n" + word.upper(), (), message=True)[0].rule == "commit_message"


def test_exclusions_cover_paths_and_references_without_matching_console_calls() -> None:
    """Named internal paths are scanned in text; a log glob matches only actual filenames."""
    directory = "docs/" + "co" + "dex/"
    specification = "docs/" + "SPEC" + "-P*.md"
    patterns = (directory, specification, "*.log")
    assert excluded_path(directory + "sample.md", patterns)
    assert excluded_path("nested/generated.log", patterns)
    assert excluded_path(specification.replace("*", "9"), patterns)
    assert (
        text_findings("", "prefix " + directory + "sample.md", patterns)[0].rule == "excluded_path"
    )
    assert text_findings("", specification.replace("*", "9"), patterns)[0].rule == "excluded_path"
    assert text_findings("", directory.removesuffix("/"), patterns)[0].rule == "excluded_path"
    assert text_findings("", "console.log(value); generated.log", patterns) == ()


def test_lock_integrity_masks_only_valid_hash_value_on_a_shared_line() -> None:
    """Other fields on the same valid JSON line remain subject to every rule."""
    segment = "j" + "lw"
    integrity = "sha512-" + "A" * 20 + "+" + segment + "+" + "A" * 61 + "=="
    assert len(integrity.removeprefix("sha512-")) == 88
    source = json.dumps({"integrity": integrity, "leak": local_path()})
    assert rules(source, "web/package-lock.json") == {"local_path"}
    assert rules(source, "other.json") == {"internal_name", "local_path"}
    assert rules(source + " invalid", "web/package-lock.json") == {"internal_name", "local_path"}


def test_invalid_or_falsely_named_hash_values_are_not_exempt() -> None:
    """A lock-field spelling cannot conceal a credential or unrelated source value."""
    value = local_path()
    assert rules(json.dumps({"integrity": value}), "package-lock.json") == {"local_path"}
    assert rules(json.dumps({"other": value}), "package-lock.json") == {"local_path"}
    source = 'hash = "sha256:' + "a" * 64 + '"\nleak = "' + value + '"\n'
    assert rules(source, "uv.lock") == {"local_path"}
    assert rules('hash = "' + value + '"\n', "uv.lock") == {"local_path"}


@pytest.mark.parametrize("value", ["token", "previous.token", "new_id()", 'new_id("")', "None"])
def test_python_nonliteral_keywords_and_assignments_are_not_credentials(value: str) -> None:
    """AST locations distinguish dynamic expressions while every other rule remains active."""
    source = (
        'label = "中文"\nresult = Lease(to' + "ken=" + value + ")\nto" + "ken = " + value + "\n"
    )
    assert rules(source, "source.py") == set()
    assert "secret" in rules(source, "source.txt")


@pytest.mark.parametrize(
    "value",
    [
        '"generated"',
        "'generated'",
        '"first" + "second"',
        "12345",
        'str("literal-secret")',
        'decode(bytes(b"literal-secret"))',
        "str(12345)",
        "str(0)",
        'f"prefix{generated}"',
    ],
)
def test_python_literal_credentials_remain_detected(value: str) -> None:
    """Literal and concatenated values do not inherit the dynamic-expression exception."""
    source = "result = Lease(to" + "ken=" + value + ")\nto" + "ken = " + value + "\n"
    assert rules(source, "source.py") == {"secret"}


def test_source_ast_never_hides_other_rules_or_noncode_values() -> None:
    """Code, environment assignments and URL query credentials retain distinct semantics."""
    source = "to" + 'ken = new_id()\npath = "' + local_path() + '"\n'
    assert rules(source, "source.py") == {"local_path"}
    assert rules("https://example.invalid/?to" + "ken=generated") == {"secret"}
    assert rules("to" + "ken == value", "source.py") == set()


def test_noreply_addresses_require_the_exact_public_domain() -> None:
    """A suffix appended to the allowed domain cannot impersonate a safe identity."""
    assert noreply_email("chaw1@users.noreply.github.com")
    assert not noreply_email("chaw1@users.noreply.github.com" + ".invalid")
    assert not noreply_email("")
