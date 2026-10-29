# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

# Logger accepted by pytest-xdist schedulers.

class Producer:
    name: str
    enabled: bool

    def __init__(self, name: str, *, enabled: bool = True) -> None: ...
    def __call__(self, *args: object, **kwargs: object) -> None: ...
    def __getattr__(self, name: str) -> Producer: ...
