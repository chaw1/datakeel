# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

# Worker operations and gateway identity used by scheduling.

from collections.abc import Sequence
from typing import Protocol

class _GatewayIdentity(Protocol):
    id: str

class WorkerController:
    gateway: _GatewayIdentity

    @property
    def shutting_down(self) -> bool: ...
    def send_runtest_some(self, indices: Sequence[int]) -> None: ...
    def shutdown(self) -> None: ...
