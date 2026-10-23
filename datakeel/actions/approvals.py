# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed approvals entry points backed by transactional storage."""

from datakeel.storage.action_approvals import approve_plan

__all__ = ["approve_plan"]
