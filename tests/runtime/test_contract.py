# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""The execution adapter persists every graph step before advancing."""

from datakeel.runtime import DURABILITY


def test_durability_requires_synchronous_checkpoint_persistence() -> None:
    """A caller cannot select eventual checkpoint durability for approval boundaries."""
    assert DURABILITY == "sync"
