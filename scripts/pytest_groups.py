# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep the real sandbox image fixture on one worker without grouping other files."""

import pytest

SECURITY_NODE_PREFIX = "tests/operators/custom_sandbox/test_security.py::"
SECURITY_GROUP = "custom-sandbox-security"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Add worker affinity only; preserve every collected item and its position."""
    for item in items:
        if item.nodeid.startswith(SECURITY_NODE_PREFIX):
            item.add_marker(pytest.mark.xdist_group(name=SECURITY_GROUP))
