# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Immutable ordered version registrations; adding versions never changes old checksums."""

from datakeel.versioning.models import MigrationDefinition
from datakeel.versioning.v1 import definition
from datakeel.versioning.v2 import definition as vector_definition


def registry() -> tuple[MigrationDefinition, ...]:
    """Assemble frozen definitions without including mutable registration code in their hashes."""
    return (definition(), vector_definition())
