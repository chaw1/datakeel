# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Why a described group of tasks became smaller, and the question when nothing is left.

Protection leaves out tasks someone else holds or that carry saved annotation unless the
words ask for them; assigning also leaves out named tasks already handed in or reviewed.
"""

from datakeel.core.intent_models import Candidate, Clarification

EXCLUSION_REASONS = {
    "held": ("在别人手上", "someone else holds them"),
    "annotated": ("已有人工标注", "they already have saved annotation"),
    "closed": (
        "已经交上去或审完, 不能再派",
        "they were handed in or reviewed and cannot be assigned",
    ),
}


def exclusion_label(excluded: dict[str, int], language: str) -> str:
    """The card line's name: left out, or only a note about tasks kept as pointed at."""
    note = all(key.startswith("kept_") for key in excluded)
    if language == "zh":
        return "提醒" if note else "已排除"
    return "Note" if note else "Left out"


def _kept_text(kept: dict[str, int], language: str) -> str:
    """Tasks located by their place that protection would have left out: kept, said."""
    reasons = {key.removeprefix("kept_"): count for key, count in kept.items()}
    if language == "zh":
        parts = [f"{count} 条{EXCLUSION_REASONS[key][0]}" for key, count in reasons.items()]
        return f" 提醒: 你点到的任务里 {', '.join(parts)}, 按你说的位置照样算在内。"
    parts = [f"{count} where {EXCLUSION_REASONS[key][1]}" for key, count in reasons.items()]
    return f" Note: of the tasks you pointed at, {'; '.join(parts)}; kept as said."


def excluded_text(excluded: dict[str, int], language: str) -> str:
    """Why a described group became smaller: protected tasks the words did not ask for."""
    kept = {key: count for key, count in excluded.items() if key.startswith("kept_")}
    excluded = {key: count for key, count in excluded.items() if key not in kept}
    if not excluded:
        return _kept_text(kept, language) if kept else ""
    total, protected = sum(excluded.values()), bool(set(excluded) - {"closed"})
    if language == "zh":
        parts = [f"{count} 条{EXCLUSION_REASONS[key][0]}" for key, count in excluded.items()]
        tail = _kept_text(kept, language) if kept else ""
        return (
            f" 排除了 {total} 条: {', '.join(parts)}{'; 话里没说要动这些' if protected else ''}。"
            + tail
        )
    parts = [f"{count} because {EXCLUSION_REASONS[key][1]}" for key, count in excluded.items()]
    tail = "; the request did not ask for them" if protected else ""
    return f" Left out {total}: {'; '.join(parts)}{tail}." + (
        _kept_text(kept, language) if kept else ""
    )


def include_question(
    left_out: dict[str, int], holder: str, action: str, language: str
) -> Clarification:
    """Every task the words describe is protected: ask to include them, never answer "none"."""
    total = sum(left_out.values())
    zh = language == "zh"
    parts = [f"{count} 条{EXCLUSION_REASONS[key][0]}" for key, count in left_out.items()]
    reasons = [f"{count} {EXCLUSION_REASONS[key][1]}" for key, count in left_out.items()]
    if zh:
        question = (
            f"{holder}符合的 {total} 条任务里 {', '.join(parts)}, 默认不动。要连这些也算上吗?"
        )
    else:
        whose = f" of {holder}" if holder else ""
        question = (
            f"All {total} matching tasks{whose} are left out by default "
            f"({'; '.join(reasons)}). Include them too?"
        )
    label = "要, 这些也算上" if zh else "Yes, include them"
    include = Candidate(id=",".join(sorted(left_out)), label=label, kind="include")
    return Clarification(
        question=question, action=action, fields=["$tasks.include"], candidates=[include]
    )
