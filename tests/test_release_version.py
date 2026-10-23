# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep the package, frontend and externally reported release synchronized."""

import json
import tomllib
from pathlib import Path

from datakeel import __version__
from datakeel.api.app import create_app
from datakeel.lineage.exports import PRODUCER
from datakeel.storage.database import Database


def test_release_version_matches_package_frontend_and_api(db: Database) -> None:
    """A release bump cannot silently leave API or UI identifiers behind."""
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())
    frontend = json.loads((root / "web/package.json").read_text())
    lock = json.loads((root / "web/package-lock.json").read_text())
    assert __version__ == project["project"]["version"] == frontend["version"]
    assert lock["version"] == lock["packages"][""]["version"] == __version__
    assert create_app(db).openapi()["info"]["version"] == __version__
    assert f"urn:datakeel:{__version__}" == PRODUCER
