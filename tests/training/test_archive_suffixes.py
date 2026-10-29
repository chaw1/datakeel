# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bind approved training archive filenames to the bytes written to disk."""

import tarfile
from pathlib import Path

from pydantic import ValidationError as SchemaValidationError

from datakeel.actions.parameters import ExportParams
from datakeel.core.errors import ValidationError
from datakeel.core.training_export_models import TRAINING_FORMATS
from datakeel.training.export_common import write_archive


def test_training_destination_rejects_unknown_suffix_before_action() -> None:
    """Every training format rejects misleading archive names at the typed boundary."""
    for format_name in sorted(TRAINING_FORMATS):
        for destination in ("bundle", "bundle.zip", "bundle.json", "bundle.gz", "bundle.TAR"):
            rejected = False
            try:
                ExportParams.model_validate(
                    {"dataset_id": "generated", "format": format_name, "destination": destination}
                )
            except SchemaValidationError as error:
                rejected = "must end in" in str(error)
            assert rejected, (format_name, destination)
        for destination in (None, "bundle.tar", "bundle.tar.gz", "bundle.tgz"):
            assert (
                ExportParams.model_validate(
                    {"dataset_id": "generated", "format": format_name, "destination": destination}
                ).destination
                == destination
            )
    for format_name in ("croissant", "openlineage"):
        assert (
            ExportParams.model_validate(
                {"dataset_id": "generated", "format": format_name, "destination": "metadata.json"}
            ).destination
            == "metadata.json"
        )


def test_direct_archive_writer_rejects_unknown_suffix_without_creating_file(tmp_path: Path) -> None:
    """Bypassing the action model cannot silently write tar bytes to an unrelated suffix."""
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "sample.txt").write_text("Generated fixture.")
    for suffix in ("", ".zip", ".json", ".gz", ".TAR"):
        output = tmp_path / f"bundle{suffix}"
        rejected = False
        try:
            write_archive(directory, output)
        except ValidationError as error:
            rejected = "must end in" in str(error)
        assert rejected, suffix
        assert not output.exists()


def test_archive_compression_matches_suffix_and_remains_deterministic(tmp_path: Path) -> None:
    """Both gzip names write gzip, while .tar writes an ordinary readable tar archive."""
    directory = tmp_path / "source"
    directory.mkdir()
    (directory / "sample.txt").write_text("Generated fixture.")
    for suffix in (".tar", ".tar.gz", ".tgz"):
        output = tmp_path / f"bundle{suffix}"
        repeated = tmp_path / f"repeated{suffix}"
        write_archive(directory, output)
        write_archive(directory, repeated)
        content = output.read_bytes()
        assert content.startswith(b"\x1f\x8b") == (suffix != ".tar")
        assert content == repeated.read_bytes()
        with tarfile.open(output) as archive:
            member = archive.extractfile("sample.txt")
            assert member is not None
            assert member.read() == b"Generated fixture."
