# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generated local sidecars shared by evidence operator unit tests."""

from pathlib import Path

import pytest

from datakeel.core.models import FileItem
from datakeel.sample_evidence import generate_samples
from tests.operators.evidence.helpers import paired_file


@pytest.fixture
def sample(tmp_path: Path) -> FileItem:
    """Provide a complete scene mentioning and annotating person and car."""
    generate_samples(tmp_path, 20)
    return paired_file(tmp_path, "train/scene-0000/image.png")
