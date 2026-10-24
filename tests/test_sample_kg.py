# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated graph samples preserve real recording texts and label synthetic long outputs."""

from pathlib import Path

from datakeel.extraction_runtime.factory import create_extractor
from datakeel.kg.loader import get_profile, get_schema
from datakeel.kg.text import chunk_text, decode_text
from datakeel.sample_kg import generate_kg_samples, recorded_documents


def test_generated_graph_samples_keep_exact_text_and_attributed_scripted_outputs(
    tmp_path: Path,
) -> None:
    """Cover all 24 recordings plus three multi-block fake sources and a failure case."""
    files = generate_kg_samples(tmp_path)
    assert len(files.paths) == 28
    assert tuple(path.read_text() for path in files.recorded) == tuple(
        item.text for item in recorded_documents()
    )
    profile, schema = get_profile("fake-long"), get_schema()
    block_count = relation_count = 0
    with create_extractor(profile) as extractor:
        for path in files.scripted:
            text = decode_text(path.read_bytes())
            assert "脚本" in text or "Scripted fixture" in text
            blocks = chunk_text(text, profile.chunk_size, profile.chunk_overlap)
            assert len(blocks) > 1
            block_count += len(blocks)
            for block in blocks:
                result = extractor.extract(block, schema)
                assert result.finish_reason == "stop"
                relation_count += len(result.output.relations)
    assert block_count > len(files.scripted)
    assert relation_count > 0
    assert files.truncated.is_file()
