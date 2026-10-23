# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Expose the shared predicate registry through the original evidence facade."""

from datakeel.core.predicate_registry import (
    predicate,
    register_predicate,
    registered_predicates,
)

__all__ = ["PREDICATES", "predicate", "register_predicate", "registered_predicates"]

# Retain the initial-vocabulary compatibility view; all validation and lookup use the registry.
PREDICATES = registered_predicates()
