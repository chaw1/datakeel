# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Optional deterministic comparison and training-text fingerprint kernels."""

from datakeel_accel._native import (
    __version__,
    compare,
    training_dice,
    training_fingerprint,
    training_shingles,
)

__all__ = ["__version__", "compare", "training_dice", "training_fingerprint", "training_shingles"]
