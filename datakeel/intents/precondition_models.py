# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Typed target and result values shared by planning preconditions."""

from collections.abc import Callable
from dataclasses import dataclass

from datakeel.core.production_models import Project
from datakeel.storage.database import Database


@dataclass(frozen=True)
class Target:
    """The objects one step acts on, plus deterministic earlier-plan effects."""

    project: Project | None
    tasks: tuple[str, ...]
    package: str | None
    actor: str
    stage: str
    assignee: str | None = None
    limit: int | None = None
    load_delta: int = 0
    prior_claims: int = 0
    reserved_tasks: frozenset[str] = frozenset()
    released_tasks: frozenset[str] = frozenset()
    uncertain: bool = False
    touched: bool = False


Found = tuple[str, dict[str, str]] | None
Check = Callable[[Database, Target], Found]
