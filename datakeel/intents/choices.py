# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Choices offered with a question about one object (P6): never a question without them.

The objects the person's own words name come first ("Package 2" in four projects offers
those four); a missing task offers the tasks the speaker holds for that work (in review for
a review); otherwise every object of the kind the speaker can see, up to five.
"""

from datakeel.core.intent_models import Candidate
from datakeel.intents.catalog import CANDIDATE_LIMIT, EntityCatalog, candidates
from datakeel.intents.drafts import DraftStep
from datakeel.intents.fill_state import FillState
from datakeel.intents.singular import which_task
from datakeel.storage.database import Database
from datakeel.storage.intent_reads import held_tasks


def object_choices(
    db: Database, step: DraftStep, field: str, kind: str, state: FillState, catalog: EntityCatalog
) -> list[Candidate]:
    """Up to five choices for the missing object ``field`` of kind ``kind``."""
    if kind == "task":
        stage = "review" if step.action == "review_task" else "annotation"
        held = held_tasks(db, state.actor, stage=stage, limit=CANDIDATE_LIMIT)
        ids = [task for _, task in held]
        return which_task(db, ids, catalog, step.action, state.language).candidates if ids else []
    said = step.said.get(field, "")
    named = catalog.match(kind, said) if said else []
    return candidates(named or catalog.of(kind))
