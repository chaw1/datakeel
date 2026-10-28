# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Standalone examples use generated fixtures and their documented file contract."""

from pathlib import Path

from jsonschema import validate
from PIL import Image

from examples.custom_operators import filter_lines, tag_images


def test_filter_lines_when_marker_supplied_writes_only_matching_fixture_lines(
    tmp_path: Path,
) -> None:
    """Keep the configured marker and return schema-valid output metadata."""
    source = tmp_path / "fixture.txt"
    source.write_text("keep first\ndiscard second\nkeep third\n", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    params = {"contains": "keep"}
    validate(params, filter_lines.PARAMETER_SCHEMA)
    result = filter_lines.run(
        [{"path": str(source), "name": source.name, "metadata": {}}],
        params,
        {"output_dir": str(output)},
    )
    assert result == [{"path": "filtered-0.txt", "metadata": {"kept_lines": 2}}]
    validate(result[0]["metadata"], filter_lines.OUTPUT_METADATA_SCHEMA)
    assert (output / result[0]["path"]).read_text() == "keep first\nkeep third"
    assert source.read_text() == "keep first\ndiscard second\nkeep third\n"


def test_tag_images_when_label_supplied_writes_rgb_fixture_with_validated_metadata(
    tmp_path: Path,
) -> None:
    """Attach caller metadata while writing a normalized PNG to the output directory."""
    source = tmp_path / "fixture.png"
    Image.new("RGBA", (12, 8), (32, 96, 160, 255)).save(source)
    output = tmp_path / "output"
    output.mkdir()
    params = {"label": "generated-fixture"}
    validate(params, tag_images.PARAMETER_SCHEMA)
    result = tag_images.run(
        [{"path": str(source), "name": source.name, "metadata": {}}],
        params,
        {"output_dir": str(output)},
    )
    validate(result[0]["metadata"], tag_images.OUTPUT_METADATA_SCHEMA)
    assert result[0]["metadata"] == {"label": "generated-fixture", "width": 12, "height": 8}
    with Image.open(output / result[0]["path"]) as image:
        assert image.mode == "RGB"
        assert image.size == (12, 8)
