# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Quality and language rules measured with independent generated text."""

import json
from pathlib import Path

import pytest

from datakeel.core.llm_data_models import TrainingConfig, TrainingSource
from datakeel.llm_data import analyze_sources, cleaned_filename
from datakeel.llm_data.checks import (
    check_record,
    has_unclosed_fence,
    redact_payload,
    repetition_ratio,
)
from datakeel.llm_data.language import estimate_tokens, identify_language
from datakeel.llm_data.parsing import parse_record


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("请详细解释恒星内部的核聚变过程以及能量是如何传递到表面的。", "zh"),
        ("The river flows through the valley and carries water to the sea.", "en"),
        ("请解释这个算法的复杂度。Please explain the time complexity of this algorithm.", "mixed"),
        ("这段代码使用Python实现排序算法并输出最终的运行结果。", "zh"),
        ("1234567890 -- !", "unknown"),
        ("Здесь описан процесс обработки данных и правила проверки.", "unknown"),
    ],
)
def test_language_scripts_and_common_words(text: str, expected: str) -> None:
    """Chinese prose with a single technical identifier remains Chinese."""
    language, confidence = identify_language(text)
    assert language == expected
    assert 0 <= confidence <= 1


@pytest.mark.parametrize(
    ("answer", "code"),
    [
        ("As an AI language model, I cannot assist with that task.", "template_response"),
        ("作为一个 AI,我无法协助完成这个任务。", "template_response"),
        ("repeat the phrase " * 15, "ngram_repetition"),
        ("Here is code:\n```python\nprint(1)", "unclosed_code_fence"),
        ("broken\ufffd\ufffd\ufffd\ufffd", "garbled_text"),
        ("<div>Some markup</div>", "html_url_residue"),
        ("Open https://example.org/article", "html_url_residue"),
    ],
)
def test_answer_quality_signals(answer: str, code: str) -> None:
    """Each heuristic describes measurable evidence rather than a model judgement."""
    parsed = parse_record(
        json.dumps({"instruction": "Explain a generated topic", "output": answer})
    )
    assert code in {item.code for item in check_record(parsed, TrainingConfig())}


def test_custom_rules_and_token_limit() -> None:
    """Phrase vocabularies and tokenizer-free bounds are frozen configuration."""
    parsed = parse_record(json.dumps({"instruction": "a" * 100, "output": "neutral coarse signal"}))
    findings = check_record(
        parsed, TrainingConfig(max_tokens=1, safety_terms=("coarse",), refusal_phrases=("neutral",))
    )
    assert {"token_limit", "safety_rule", "template_response"} <= {item.code for item in findings}
    assert estimate_tokens("中文") == 2
    assert repetition_ratio("The night is clear and the stars shine in a distant sky.") < 0.1


def test_language_balanced_sentence_is_mixed() -> None:
    """A fully bilingual record exposes a mixed label instead of majority-script guessing."""
    language, _confidence = identify_language(
        "请解释数据处理流程和检查规则。Please explain the processing flow and validation rules."
    )
    assert language == "mixed"


def test_privacy_when_tool_arguments_and_schema_descriptions_contain_secrets_redacts_all(
    tmp_path: Path,
) -> None:
    """Privacy scans every payload string, including fields absent from visible answer text."""
    secret = "sk-" + "q7R8s9T0" * 4
    payload = {
        "tools": [
            {
                "type": "function",
                "function": {"name": "lookup", "description": "Owner admin@example.org"},
            }
        ],
        "messages": [
            {"role": "user", "content": "Find the saved contact."},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "lookup",
                            "arguments": json.dumps(
                                {"email": "contact@example.net", "api_key": secret}
                            ),
                        },
                    }
                ],
            },
            {"role": "tool", "tool_call_id": "call-1", "content": "Located the contact."},
            {"role": "assistant", "content": "The contact has been located."},
        ],
    }
    parsed = parse_record(json.dumps(payload))
    findings = check_record(parsed, TrainingConfig())
    assert {"pii_email", "pii_secret"} <= {item.code for item in findings}
    assert any(item.field.endswith("function.arguments") for item in findings)
    assert any(item.field.endswith("function.description") for item in findings)
    redacted = json.dumps(redact_payload(parsed.payload))
    assert secret not in redacted
    assert "contact@example.net" not in redacted
    assert "admin@example.org" not in redacted
    assert "[EMAIL]" in redacted
    assert "[SECRET]" in redacted
    path = tmp_path / "tool.jsonl"
    path.write_text(json.dumps(payload) + "\n")
    report = analyze_sources(
        (TrainingSource(file_id="tool", filename=path.name, path=str(path)),),
        cleaned_dir=tmp_path / "cleaned",
    )
    persisted = (tmp_path / "cleaned" / cleaned_filename("tool")).read_text()
    assert report.redacted == 1
    assert secret not in persisted
    assert "contact@example.net" not in persisted
    assert "admin@example.org" not in persisted


def test_rejected_when_code_fence_is_unclosed_always_reports_truncation() -> None:
    """Ignoring the rejected branch must fail this independent mutation anchor."""
    record = parse_record(
        json.dumps(
            {
                "prompt": "Explain the mechanism.",
                "chosen": "A complete explanation.",
                "rejected": "```python\nprint(1)",
            }
        )
    )
    assert any(
        item.code == "unclosed_code_fence" for item in check_record(record, TrainingConfig())
    )


@pytest.mark.parametrize(
    ("chosen", "rejected", "field", "code"),
    [
        ("A useful explanation.", "```python\nprint(1)", "rejected", "unclosed_code_fence"),
        ("```python\nprint(1)", "A different explanation.", "chosen", "unclosed_code_fence"),
        (
            "A useful explanation.",
            "as an ai language model I cannot help",
            "rejected",
            "template_response",
        ),
        ("A useful explanation.", "repeat three words " * 30, "rejected", "ngram_repetition"),
    ],
)
def test_preference_quality_when_either_branch_is_bad_reports_its_field(
    chosen: str,
    rejected: str,
    field: str,
    code: str,
) -> None:
    """Rejected responses receive the same deterministic quality and truncation checks."""
    parsed = parse_record(
        json.dumps({"prompt": "Explain the mechanism.", "chosen": chosen, "rejected": rejected})
    )
    findings = check_record(parsed, TrainingConfig())
    assert any(item.code == code and item.field == field for item in findings)


def test_message_fences_when_unclosed_in_separate_turns_do_not_cancel_each_other() -> None:
    """Two individually truncated answers cannot look balanced after string concatenation."""
    parsed = parse_record(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "First question"},
                    {"role": "assistant", "content": "```python\nprint(1)"},
                    {"role": "user", "content": "Second question"},
                    {"role": "assistant", "content": "```python\nprint(2)"},
                ]
            }
        )
    )
    findings = check_record(parsed, TrainingConfig())
    assert sum(item.code == "unclosed_code_fence" for item in findings) == 2


def test_privacy_field_paths_when_metadata_key_looks_private_never_echo_key() -> None:
    """Only safe field identifiers appear in public issue paths."""
    parsed = parse_record(
        json.dumps(
            {
                "instruction": "Explain a harmless concept.",
                "output": "A normal explanation.",
                "metadata": {
                    "owner@example.org": "person@example.net",
                    "enabled": True,
                    "score": 1.25,
                },
            }
        )
    )
    findings = check_record(parsed, TrainingConfig())
    assert all("owner@example.org" not in item.field for item in findings)
    assert any(item.code == "pii_email" for item in findings)
    assert "owner@example.org" not in json.dumps(redact_payload(parsed.payload))


def test_privacy_when_redacted_metadata_keys_collide_retains_each_value() -> None:
    """Redaction never overwrites two private metadata fields sharing a type label."""
    redacted = redact_payload({"a@example.org": "first", "b@example.net": "second"})
    assert isinstance(redacted, dict)
    assert len(redacted) == 2
    assert set(redacted.values()) == {"first", "second"}


@pytest.mark.parametrize("label", ["api_key", "password", "client_secret", "AWS_SECRET_ACCESS_KEY"])
def test_nested_labelled_credential_when_value_has_no_prefix_detects_and_cleans(
    label: str,
    tmp_path: Path,
) -> None:
    """Field context survives the recursive payload walk and the actual cleaned artifact."""
    value = "q7R8s9T0" * 4
    path = tmp_path / "labeled.jsonl"
    path.write_text(
        json.dumps(
            {
                "instruction": "Explain a generated concept.",
                "output": "A complete explanation.",
                "metadata": {label: value},
            }
        )
        + "\n"
    )
    report = analyze_sources(
        (TrainingSource(file_id="labelled", filename=path.name, path=str(path)),),
        cleaned_dir=tmp_path / "cleaned",
    )
    assert report.pii_records == 1
    assert report.redacted == 1
    finding = next(item for item in report.samples[0].issues if item.code == "pii_secret")
    assert finding.field == f"payload.metadata.{label}"
    assert finding.start == 0
    assert finding.end == len(value)
    content = json.loads((tmp_path / "cleaned" / cleaned_filename("labelled")).read_text())
    assert content["metadata"][label] == "[SECRET]"


def test_code_fence_when_markers_appear_inside_code_never_flags_valid_block() -> None:
    """Inline string markers and shorter nested fences cannot close the outer fence."""
    assert not has_unclosed_fence('```python\nprint("```")\n```')
    assert not has_unclosed_fence("````markdown\n```python\ncode\n```\n````")
    assert not has_unclosed_fence("An inline ``` marker is not a fenced block.")
    assert not has_unclosed_fence("~~~text\ncontent\n~~~")
    assert has_unclosed_fence("````text\ncontent\n```")


def test_code_fence_when_tilde_block_is_unclosed_reports_truncation() -> None:
    """Both supported Markdown fence characters must pair before a response is complete."""
    parsed = parse_record(
        json.dumps({"instruction": "Provide sample code", "output": "~~~python\nprint(1)"})
    )
    assert "unclosed_code_fence" in {item.code for item in check_record(parsed, TrainingConfig())}
