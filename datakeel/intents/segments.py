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
from datakeel.storage.production_leases import RETURN_STATE

NEXT = re.compile(
    r"接下来|再往后|往后|后面的|之后的|再后面|随后的|下一批|下面的|然后的|另一|剩下的|"
    r"\bnext\b|\bfollowing\b|\bafter (?:those|that|them)\b|\bthe other\b|\banother\b",
    re.IGNORECASE,
)


def _key(spec: dict[str, JsonValue]) -> str:
    return json.dumps(spec, sort_keys=True, ensure_ascii=False)


def _segmented(spec: dict[str, JsonValue], state: FillState, action: str) -> bool:
    """The first N said again after an earlier step took some by place: the next N.

    "接下来两条" says so; one action given the same first N twice ("the first to Lucy and the
    other one to 赵敏") cannot mean the same tasks either.
    """
    first = spec.get("first")
    counted = isinstance(first, int) and not isinstance(first, bool) and first > 0
    if not counted or not state.taken:
        return False
    return NEXT.search(state.text) is not None or action in state.taken


def freed_snapshots(snapshots: list[TaskSnapshot], state: FillState) -> list[TaskSnapshot]:
    """A task an earlier step takes back is free, and back in the queue, when this step runs."""
    return [
        task.model_copy(update={"holder": None, "stage": None, "state": RETURN_STATE[task.stage]})
        if task.stage is not None and state.freed.get(task.id) == task.stage
        else task
        for task in snapshots
    ]


def later_segment(
    spec: dict[str, JsonValue], snapshots: list[TaskSnapshot], state: FillState, action: str
) -> list[TaskSnapshot]:
    """For "接下来两条", the first N counted after the tasks earlier steps took by place."""
    if not _segmented(spec, state, action):
        return snapshots
    taken = {task for ids in state.taken.values() for task in ids}
    return [task for task in snapshots if task.id not in taken]


Found = tuple[list[str], dict[str, int]] | Clarification


def once(
    spec: dict[str, JsonValue], state: FillState, action: str, resolve: Callable[[], Found]
) -> Found:
    """One group named for two steps covers what the earlier step took ("收回再全派给 X")."""
    found = resolve()
    if isinstance(found, Clarification):
        return found
    ids, left_out = found
    same = [] if _segmented(spec, state, action) else state.chosen.get(_key(spec), [])
    merged = [*same, *(task for task in ids if task not in same)]
    state.chosen.setdefault(_key(spec), list(merged))
    if "first" in spec:
        state.taken.setdefault(action, []).extend(merged)
    return merged, left_out
