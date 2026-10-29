# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stream recovery, privacy-safe ledger and reproducible record cleaning."""

import hashlib
import json
from pathlib import Path

import pytest

from datakeel.core.llm_data_models import TrainingConfig, TrainingRecord, TrainingSource
from datakeel.llm_data import analyze_sources, cleaned_filename


def source(tmp_path: Path, lines: list[object], *, name: str = "data.jsonl") -> TrainingSource:
    """Write generated data with stable file identity and optional raw bad lines."""
    path = tmp_path / name
    path.write_text(
        "\n".join(
            line if isinstance(line, str) else json.dumps(line, ensure_ascii=False)
            for line in lines
        )
        + "\n"
    )
    return TrainingSource(file_id=name, path=str(path), filename=name)


def test_mixed_formats_bad_lines_and_stable_identity(tmp_path: Path) -> None:
    """A bad line between valid formats cannot abort later records or change line numbers."""
    data = source(
        tmp_path,
        [
            {
                "messages": [
                    {"role": "user", "content": "What is a star?"},
                    {"role": "assistant", "content": "A luminous sphere of plasma."},
                ]
            },
            "{broken",
            {"instruction": "请介绍月球的公转轨道", "output": "月球绕地球公转,轨道是一个椭圆。"},
            {"prompt": "Choose a shape", "chosen": "A circle", "rejected": "A cube"},
        ],
    )
    first = analyze_sources((data,))
    second = analyze_sources((data,))
    assert first == second
    assert first.records == 4
    assert first.valid_records == 3
    assert first.samples[1].line == 2
    assert first.samples[1].issues[0].code == "format_error"
    assert first.formats == {"messages": 1, "instruction": 1, "preference": 1}
    assert all(item.id.startswith(f"{data.file_id}:{item.line}:") for item in first.samples)


def test_dry_run_ledger_cleans_redacts_and_explains_every_record(tmp_path: Path) -> None:
    """Drop duplicates and bad rows, redact PII, and leave the immutable source unchanged."""
    address = "reader" + "@example.org"
    data = source(
        tmp_path,
        [
            {"instruction": "Contact details", "output": f"Write to {address} for help."},
            {"instruction": "Describe an ocean", "output": "A vast body of salt water."},
            {"instruction": "DESCRIBE AN OCEAN!", "output": "A VAST body of salt water."},
            {"prompt": "Pick one", "chosen": "same", "rejected": "same"},
            "not json",
        ],
    )
    original = Path(data.path).read_bytes()
    ledger = tmp_path / "ledger.jsonl"
    report = analyze_sources((data,), ledger_path=ledger, cleaned_dir=tmp_path / "clean")
    decisions = [
        TrainingRecord.model_validate_json(line) for line in ledger.read_text().splitlines()
    ]
    assert [item.decision for item in decisions] == ["redact", "keep", "drop", "drop", "drop"]
    assert all(item.reasons for item in decisions)
    assert report.ledger_sha256 == hashlib.sha256(ledger.read_bytes()).hexdigest()
    assert address not in ledger.read_text()
    cleaned = (tmp_path / "clean" / cleaned_filename(data.file_id)).read_text()
    assert "[EMAIL]" in cleaned
    assert address not in cleaned
    assert len(cleaned.splitlines()) == 2
    assert Path(data.path).read_bytes() == original
    assert report.pii_records == 1


def test_oversized_invalid_unicode_and_blank_lines_do_not_abort(tmp_path: Path) -> None:
    """Read and drain oversized physical lines using bounded chunks and real content hashes."""
    path = tmp_path / "mixed.jsonl"
    large = b"x" * 5000 + b"\n"
    path.write_bytes(large + b"\xff\n\n" + b'{"instruction":"Question","output":"Answer"}\n')
    data = TrainingSource(file_id="mixed", path=str(path), filename=path.name)
    report = analyze_sources((data,), TrainingConfig(max_line_bytes=1024))
    assert report.records == 4
    assert report.valid_records == 1
    assert report.samples[0].content_hash == hashlib.sha256(large).hexdigest()
    assert report.issue_counts["line_too_large"] == 1
    assert report.issue_counts["format_error"] == 2


def test_sample_limit_never_limits_full_ledger_or_totals(tmp_path: Path) -> None:
    """Bound summaries independently of record count and audit completeness."""
    data = source(
        tmp_path,
        [
            {"instruction": f"Explain {index}", "output": f"Value {index} is generated"}
            for index in range(100)
        ],
    )
    ledger = tmp_path / "ledger"
    report = analyze_sources((data,), TrainingConfig(sample_limit=2), ledger_path=ledger)
    assert report.records == 100
    assert len(report.samples) == 2
    assert len(ledger.read_text().splitlines()) == 100
    assert len(report.duplicate_clusters) <= 2


def test_invalid_record_never_consumes_a_good_duplicate_representative(tmp_path: Path) -> None:
    """A structural error cannot cause the sole valid copy to be removed in cleaning."""
    data = source(
        tmp_path,
        [
            {"messages": [{"role": "assistant", "content": "A clear answer"}]},
            {"instruction": "A clear", "output": "answer"},
        ],
    )
    report = analyze_sources((data,))
    assert [item.decision for item in report.samples] == ["drop", "keep"]


def test_invalid_record_never_exposes_encoded_or_partial_private_payload(tmp_path: Path) -> None:
    """Invalid JSON cannot be reliably decoded or redacted, so its raw preview stays hidden."""
    raw = '{"instruction":"Contact", "output":"reader\\u0040example.org",}'
    data = source(tmp_path, [raw])
    ledger = tmp_path / "private-decisions.jsonl"
    report = analyze_sources((data,), ledger_path=ledger)
    assert report.samples[0].preview == "[UNPARSEABLE_RECORD]"
    assert "reader" not in ledger.read_text()
    assert report.samples[0].content_hash
    assert "column" in report.samples[0].issues[0].message


@pytest.mark.parametrize("with_cleaned", [False, True])
@pytest.mark.parametrize(
    "bad",
    [
        {"instruction": chr(0xD800), "output": "A harmless response."},
        {"instruction": "A generated request.", "output": chr(0xDC00)},
        {
            "messages": [
                {"role": "user", "content": chr(0xD800)},
                {"role": "assistant", "content": "A harmless response."},
            ]
        },
        {
            "instruction": "Request",
            "output": "Response",
            "metadata": {"nested": [{"value": chr(0xD800)}]},
        },
        {
            "instruction": "Request",
            "output": "Response",
            "metadata": {"nested": [{chr(0xDC00): "ordinary"}]},
        },
        {
            "instruction": "Request",
            "output": "Response",
            "metadata": {"nested": [{chr(0xD800): chr(0xDC00)}]},
        },
    ],
)
def test_escaped_lone_surrogate_when_first_row_is_bad_preserves_following_record(
    bad: object,
    tmp_path: Path,
    *,
    with_cleaned: bool,
) -> None:
    """Invalid scalar values anywhere in a record become isolated safe format errors."""
    good = {
        "instruction": "Describe the generated object.",
        "output": "The object is a smooth sphere.",
    }
    data = source(tmp_path, [json.dumps(bad, ensure_ascii=True), good])
    ledger = tmp_path / "surrogate-ledger.jsonl"
    report = analyze_sources(
        (data,),
        ledger_path=ledger,
        cleaned_dir=tmp_path / "clean" if with_cleaned else None,
    )
    assert report.records == 2
    assert report.valid_records == 1
    assert report.issue_counts == {"format_error": 1}
    assert [item.decision for item in report.samples] == ["drop", "keep"]
    assert [item.line for item in report.samples] == [1, 2]
    assert report.samples[0].preview == "[UNPARSEABLE_RECORD]"
    assert (
        report.samples[0].issues[0].message
        == "JSON strings must contain valid Unicode scalar values"
    )
    encoded = ledger.read_text()
    assert len(encoded.splitlines()) == 2
    assert r"\ud800" not in encoded
    assert r"\udc00" not in encoded
    if with_cleaned:
        cleaned = (tmp_path / "clean" / cleaned_filename(data.file_id)).read_text()
        assert [json.loads(line) for line in cleaned.splitlines()] == [good]


@pytest.mark.parametrize("with_cleaned", [False, True])
@pytest.mark.parametrize("ascii_escapes", [False, True])
def test_valid_unicode_scalar_or_escaped_pair_survives_analysis_and_cleaning(
    tmp_path: Path,
    *,
    with_cleaned: bool,
    ascii_escapes: bool,
) -> None:
    """Normal UTF-8 emoji and a legal JSON surrogate pair both remain ordinary data."""
    payload = {
        "instruction": "Explain this face " + chr(0x1F603),
        "output": "It is smiling.",
        "metadata": {"symbol": chr(0x1F603), "count": 1},
    }
    data = source(tmp_path, [json.dumps(payload, ensure_ascii=ascii_escapes)])
    report = analyze_sources((data,), cleaned_dir=tmp_path / "clean" if with_cleaned else None)
    assert report.records == 1
    assert report.valid_records == 1
    assert not report.issue_counts
    if with_cleaned:
        cleaned = (tmp_path / "clean" / cleaned_filename(data.file_id)).read_text()
        assert json.loads(cleaned) == payload


def test_unicode_scalar_guard_when_removed_cannot_abort_the_cleaning_stream(tmp_path: Path) -> None:
    """The scalar-validation mutation must cause an observed assertion failure."""
    data = source(
        tmp_path,
        [
            json.dumps(
                {"instruction": "Request", "output": "Response", "metadata": {chr(0xD800): "value"}}
            ),
            {"instruction": "Describe a harmless object.", "output": "It is a sphere."},
        ],
    )
    completed = False
    try:
        report = analyze_sources((data,), cleaned_dir=tmp_path / "clean")
        completed = report.records == 2 and report.valid_records == 1
    except UnicodeEncodeError:
        completed = False
    assert completed
