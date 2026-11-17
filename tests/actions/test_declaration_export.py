# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frontend descriptions come from actual owners with independent expected phrases."""

import json

import pytest

from scripts.export_action_declarations import main


def test_frontend_export_uses_declared_phrases(capsys: pytest.CaptureFixture[str]) -> None:
    """Generated labels preserve known bilingual titles and the closed generic widget."""
    main()
    data = json.loads(capsys.readouterr().out)
    assert data == {
        "quarantine_files": {
            "phrases": {"zh": ["隔离文件"], "en": ["quarantine files"]},
            "widget": "generic",
            "titles": {"zh": "隔离文件", "en": "Quarantine files"},
        },
        "unquarantine_files": {
            "phrases": {"zh": ["取消隔离"], "en": ["unquarantine files"]},
            "widget": "generic",
            "titles": {"zh": "取消隔离", "en": "Unquarantine files"},
        },
    }
