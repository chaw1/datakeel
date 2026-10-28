# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Stream recovery, privacy-safe ledger and reproducible record cleaning."""

import hashlib
import json
from pathlib import Path

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
