# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Canonical file selection schema shared with action declarations."""

from datakeel.core.models import BoundaryModel
from datakeel.ontology.models import ObjectSet


class SelectionParams(BoundaryModel):
    """Resolve a file ObjectSet to a frozen manifest before changing state."""

    selection: ObjectSet
