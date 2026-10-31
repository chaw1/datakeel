# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Task groups across the steps of one plan: the same group twice, or the next segment.

"把小王手上的收回再派给小李" names one group for two steps: the second step acts on the
tasks the first one took, so a task protection kept out of the first is untouched by both.
"前两条派给小王, 接下来两条派给小李" counts the second "first two" after the ones an
earlier step already took.
"""

import json
import re
from collections.abc import Callable

from pydantic import JsonValue

from datakeel.core.intent_models import Clarification
from datakeel.intents.fill_state import FillState
from datakeel.storage.intent_reads import TaskSnapshot

NEXT = re.compile(
    r"接下来|再往后|往后|后面的|之后的|再后面|随后的|下一批|下面的|然后的|"
    r"\bnext\b|\bfollowing\b|\bafter (?:those|that|them)\b",
    re.IGNORECASE,
)


def _key(spec: dict[str, JsonValue]) -> str:
    return json.dumps(spec, sort_keys=True, ensure_ascii=False)


def _segmented(spec: dict[str, JsonValue], state: FillState) -> bool:
    first = spec.get("first")
    counted = isinstance(first, int) and not isinstance(first, bool) and first > 0
    return counted and bool(state.taken) and NEXT.search(state.text) is not None


def later_segment(
    spec: dict[str, JsonValue], snapshots: list[TaskSnapshot], state: FillState
) -> list[TaskSnapshot]:
    """For "接下来两条", the first N counted after the tasks earlier steps took by place."""
    if not _segmented(spec, state):
        return snapshots
    taken = set(state.taken)
    return [task for task in snapshots if task.id not in taken]


Found = tuple[list[str], dict[str, int]] | Clarification


def once(spec: dict[str, JsonValue], state: FillState, resolve: Callable[[], Found]) -> Found:
    """One group named for two steps is the same tasks; otherwise resolve and remember it."""
    same = None if _segmented(spec, state) else state.chosen.get(_key(spec))
    found: Found = (list(same), {}) if same else resolve()
    if not isinstance(found, Clarification):
        state.chosen.setdefault(_key(spec), list(found[0]))
        if "first" in spec:
            state.taken.extend(found[0])
    return found
