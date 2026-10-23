# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Disable external tracing regardless of inherited environment switches."""

from collections.abc import Generator
from contextlib import AbstractContextManager, contextmanager
from typing import Literal, Protocol, cast

import langsmith

langsmith.configure(enabled=False)


class _TracingAPI(Protocol):
    def tracing_context(
        self, *, enabled: bool, parent: Literal[False]
    ) -> AbstractContextManager[None]: ...


@contextmanager
def tracing_disabled() -> Generator[None]:
    """Apply the installed SDK's global and invocation-local tracing disable APIs."""
    langsmith.configure(enabled=False)
    with cast("_TracingAPI", langsmith).tracing_context(enabled=False, parent=False):
        yield
