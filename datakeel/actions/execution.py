# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed execution entry points backed by transactional storage."""

from datakeel.storage.action_execution import execute_plan

__all__ = ["execute_plan"]
