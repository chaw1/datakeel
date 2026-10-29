# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Isolate real sandbox execution and schedule known long cases early."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scripts.pytest_priorities import prioritize_tests
from scripts.pytest_scheduler import ExclusiveSecurityScheduling

if TYPE_CHECKING:
    from xdist.remote import Producer

SECURITY_NODE_PREFIX = "tests/operators/custom_sandbox/test_security.py::"
SECURITY_GROUP = "custom-sandbox-security"


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items: list[pytest.Item], config: pytest.Config) -> None:
    """Preserve selection and use the same stable ordering on every parallel worker."""
    for item in items:
        if item.nodeid.startswith(SECURITY_NODE_PREFIX):
            item.add_marker(pytest.mark.xdist_group(name=SECURITY_GROUP))
    if hasattr(config, "workerinput"):
        prioritize_tests(items)


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_make_scheduler(
    config: pytest.Config, log: Producer
) -> ExclusiveSecurityScheduling | None:
    """Complete the sandbox group before releasing ordinary parallel work."""
    if config.getoption("dist") == "loadgroup":
        return ExclusiveSecurityScheduling(config, log)
    return None
