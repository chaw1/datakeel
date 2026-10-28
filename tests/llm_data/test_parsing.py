# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent positive and negative fixtures for supported training formats."""

import json

import pytest

from datakeel.llm_data.parsing import parse_record


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        (
            {
                "messages": [
                    {"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Answer"},
                ]
            },
            "messages",
        ),
        ({"instruction": "Explain", "input": "Context", "output": "Answer"}, "instruction"),
        ({"prompt": "Question", "chosen": "Good answer", "rejected": "Bad answer"}, "preference"),
        (
            {
                "prompt": [{"role": "user", "content": "Question"}],
                "chosen": [{"role": "assistant", "content": "Good"}],
                "rejected": [{"role": "assistant", "content": "Bad"}],
            },
            "preference",
        ),
        (
            {
                "chosen": [
                    {"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Good"},
                ],
                "rejected": [
                    {"role": "user", "content": "Question"},
                    {"role": "assistant", "content": "Bad"},
                ],
            },
            "preference",
        ),
    ],
)
def test_supported_formats_detected_without_structure_errors(
    payload: object, expected: str
) -> None:
    """Conversation suffixes and full preference conversations are both ordinary data."""
    record = parse_record(json.dumps(payload))
    assert record.format == expected
    assert record.prompt
    assert not record.issues


@pytest.mark.parametrize(
    "raw",
    [
        "{",
        "null",
        "[]",
        "12",
        '{"x": "unknown"}',
        '{"messages": []}',
        '{"messages":[42]}',
        '{"instruction":"ok","output":3}',
    ],
)
def test_bad_lines_are_rejected_independently(raw: str) -> None:
    """Wrong JSON shapes never silently become valid SFT records."""
    with pytest.raises((ValueError, TypeError)):
        parse_record(raw)


@pytest.mark.parametrize(
    ("roles", "code"),
    [
        (["assistant"], "role_order"),
        (["user", "user", "assistant"], "role_order"),
        (["user", "system", "assistant"], "role_order"),
        (["system", "user"], "missing_final_assistant"),
        (["user", "tool", "assistant"], "role_order"),
    ],
)
def test_role_rules_detect_invalid_sequences(roles: list[str], code: str) -> None:
    """System position, alternating turns and a final assistant are separate guards."""
    parsed = parse_record(
        json.dumps(
            {
                "messages": [
                    {
                        "role": role,
                        "content": "content",
                        **({"tool_call_id": "unrequested"} if role == "tool" else {}),
                    }
                    for role in roles
                ]
            }
        )
    )
    assert code in {item.code for item in parsed.issues}


def test_tool_calls_and_text_blocks_are_supported() -> None:
    """A tool exchange between assistant turns is legitimate tool conversation data."""
    parsed = parse_record(
        json.dumps(
            {
                "tools": [],
                "messages": [
                    {"role": "system", "content": "Helpful instructions"},
                    {"role": "user", "content": [{"type": "text", "text": "Read the temperature"}]},
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call-one",
                                "type": "function",
                                "function": {"name": "read", "arguments": "{}"},
                            }
                        ],
                    },
                    {"role": "tool", "tool_call_id": "call-one", "content": "20 degrees"},
                    {"role": "assistant", "content": "The temperature is twenty degrees."},
                ],
            }
        )
    )
    assert not parsed.issues
    assert "twenty" in parsed.answer


def test_manual_format_never_silently_falls_back() -> None:
    """Explicit format declarations are checked against their own required fields."""
    with pytest.raises(ValueError, match="messages"):
        parse_record('{"instruction":"Question","output":"Answer"}', "messages")


def test_chosen_empty_is_a_specific_preference_signal() -> None:
    """Empty chosen answers remain inspectable rather than becoming an opaque bad line."""
    parsed = parse_record('{"prompt":"Question","chosen":[],"rejected":"Bad"}')
    assert "chosen_empty" in {item.code for item in parsed.issues}


def _call(identity: str = "call-a") -> dict[str, object]:
    return {
        "id": identity,
        "type": "function",
        "function": {"name": "lookup", "arguments": "{}"},
    }


def _exchange(calls: object, results: list[dict[str, object]]) -> dict[str, object]:
    return {
        "messages": [
            {"role": "user", "content": "Look up two measurements."},
            {"role": "assistant", "content": None, "tool_calls": calls},
            *results,
            {"role": "assistant", "content": "The measurement lookup has completed."},
        ]
    }


@pytest.mark.parametrize(
    "calls",
    [
        "not-an-array",
        ["not-an-object"],
        [{"id": "a", "type": "function"}],
        [{"id": 1, "type": "function", "function": {"name": "lookup", "arguments": "{}"}}],
        [{"id": "a", "type": "unknown", "function": {"name": "lookup", "arguments": "{}"}}],
        [{"id": "a", "type": "function", "function": {"name": " ", "arguments": "{}"}}],
        [{"id": "a", "type": "function", "function": {"name": "lookup", "arguments": {}}}],
        [_call(), _call()],
    ],
)
def test_tool_calls_when_schema_invalid_reject_with_safe_field_reason(calls: object) -> None:
    """Required call fields are validated before message text can be processed."""
    with pytest.raises((TypeError, ValueError), match="tool_calls"):
        parse_record(json.dumps(_exchange(calls, [])))


def test_parallel_tool_results_when_reordered_match_outstanding_ids() -> None:
    """Multiple results may arrive in a different order before the final assistant."""
    parsed = parse_record(
        json.dumps(
            _exchange(
                [_call("a"), _call("b")],
                [
                    {"role": "tool", "tool_call_id": "b", "content": "Second value"},
                    {"role": "tool", "tool_call_id": "a", "content": "First value"},
                ],
            )
        )
    )
    assert not parsed.issues


@pytest.mark.parametrize(
    "results",
    [
        [],
        [{"role": "tool", "tool_call_id": "wrong", "content": "value"}],
        [
            {"role": "tool", "tool_call_id": "a", "content": "value"},
            {"role": "tool", "tool_call_id": "a", "content": "another value"},
        ],
    ],
)
def test_tool_results_when_missing_unknown_or_repeated_report_role_order(
    results: list[dict[str, object]],
) -> None:
    """Tool-role placement alone cannot substitute for a matching call identity."""
    parsed = parse_record(json.dumps(_exchange([_call("a")], results)))
    assert "role_order" in {item.code for item in parsed.issues}


def test_tool_result_when_id_missing_rejects_missing_field() -> None:
    """A valid tool role still requires an explicit result identity."""
    with pytest.raises(TypeError, match="tool_call_id"):
        parse_record(json.dumps(_exchange([_call()], [{"role": "tool", "content": "value"}])))


def test_tool_calls_when_attached_to_user_message_rejects_invalid_owner() -> None:
    """A user cannot declare tool invocations as if it were the assistant."""
    with pytest.raises(TypeError, match="assistant"):
        parse_record(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "Question", "tool_calls": [_call()]},
                        {"role": "assistant", "content": "Answer"},
                    ]
                }
            )
        )


@pytest.mark.parametrize("roles", [["assistant"], ["user", "user"], ["user", "system", "user"]])
def test_preference_prompt_when_roles_invalid_reports_structure(roles: list[str]) -> None:
    """Preference prefixes obey the same ordering and end with a user request."""
    parsed = parse_record(
        json.dumps(
            {
                "prompt": [{"role": role, "content": "content"} for role in roles],
                "chosen": "A detailed first response.",
                "rejected": "An unrelated alternative.",
            }
        )
    )
    assert "role_order" in {item.code for item in parsed.issues}


def test_preference_full_histories_when_prior_assistant_changes_reports_mismatch() -> None:
    """Earlier assistant context belongs to the prompt identity, not to the completion."""
    first = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier context A"},
        {"role": "user", "content": "Current question"},
    ]
    second = [
        {"role": "user", "content": "Earlier question"},
        {"role": "assistant", "content": "Earlier context B"},
        {"role": "user", "content": "Current question"},
    ]
    parsed = parse_record(
        json.dumps(
            {
                "chosen": [*first, {"role": "assistant", "content": "Preferred answer"}],
                "rejected": [*second, {"role": "assistant", "content": "Other answer"}],
            }
        )
    )
    assert "preference_prompt_mismatch" in {item.code for item in parsed.issues}
    assert "Earlier context A" in parsed.prompt
    assert parsed.answer == "Preferred answer"
    assert parsed.rejected == "Other answer"


def test_preference_full_histories_when_same_and_explicit_prompt_match_pass() -> None:
    """Explicit message prefixes and full conversation branches can coexist."""
    prefix = [
        {"role": "system", "content": "Be clear."},
        {"role": "user", "content": "Current question"},
    ]
    parsed = parse_record(
        json.dumps(
            {
                "prompt": prefix,
                "chosen": [*prefix, {"role": "assistant", "content": "Preferred answer"}],
                "rejected": [*prefix, {"role": "assistant", "content": "Other answer"}],
            }
        )
    )
    assert not parsed.issues


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "1e999"])
def test_json_when_nonfinite_number_present_rejects_without_echoing_payload(value: str) -> None:
    """Nonstandard and overflowing numbers cannot silently enter canonical JSON."""
    raw = '{"instruction":"Question","output":"Answer","metadata":' + value + "}"
    with pytest.raises(ValueError, match=r"^Non-finite JSON numbers are not permitted$"):
        parse_record(raw)


def test_preference_when_null_chosen_reports_chosen_empty() -> None:
    """Null completions have the same inspectable empty signal as an empty array."""
    parsed = parse_record('{"prompt":"Question","chosen":null,"rejected":"Other"}')
    assert "chosen_empty" in {item.code for item in parsed.issues}
