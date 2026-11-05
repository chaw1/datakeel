# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Dataset persistence adapters; application results are frozen validated models.

Session-bound helpers are internal adapters for legacy storage wiring, never domain ports.
The caller opening a write session owns its only commit; helpers only flush.
"""
