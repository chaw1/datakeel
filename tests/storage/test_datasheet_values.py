# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Documentation facts exclude private locations and credential-shaped content."""

from pathlib import PurePosixPath
from urllib.parse import urlencode

import pytest

from datakeel.core.models import utcnow
from datakeel.storage.datasheet_values import make_fact, public_value


@pytest.mark.parametrize(
    "value",
    [
        "Bearer generated-secret",
        "sk-" + "a" * 24,
        "file " + str(PurePosixPath("/") / "home" / "generated" / "private.txt"),
        "C:\\generated\\file.txt",
        "https://name:password@example.test/file",
        "http://localhost/file",
        "http://127.0.0.1/file",
        "https://example.test/file?" + urlencode({"token": "generated"}),
        "http://[invalid/file",
        str(PurePosixPath("/") / "single"),
        "file://" + str(PurePosixPath("/") / "generated" / "input.txt"),
        "AKIA" + "A" * 16,
        "-----BEGIN " + "PRIVATE KEY-----",
        "http://fixture.internal/file",
    ],
)
def test_unsafe_string_is_omitted(value: str) -> None:
    """Discard complete strings when any embedded location or secret cannot be public."""
    assert public_value(value) is None
    assert make_fact("maintenance", "dataset", "fixture", "owner", value, utcnow()) is None


def test_nested_values_remove_private_keys_but_keep_public_license_and_measurements() -> None:
    """Keep supported JSON values while recursively pruning sensitive children."""
    assert public_value(
        {
            "owner": "Research group",
            "password": "private",
            "nested": {"object_key": "private", "count": 2},
            "list": [True, None, "Bearer generated-secret"],
            "license": "https://spdx.org/licenses/CC0-1.0.html",
        }
    ) == {
        "owner": "Research group",
        "nested": {"count": 2},
        "list": [True],
        "license": "https://spdx.org/licenses/CC0-1.0.html",
    }
