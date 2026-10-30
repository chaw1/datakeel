# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Common multi-step requests recognised without a model, in Chinese and English."""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from datakeel.intents.drafts import DraftStep, IntentDraft, language_of

if TYPE_CHECKING:
    from pydantic import JsonValue

_ZH_SETUP = re.compile(
    r"(?:建|创建|新建|搭|开)(?:一个|个|一套)?(?P<labels>[^\uff0c。,\uff1b;]{1,30}?)"
    r"(?P<shape>框|多边形|关键点|分类|文本)?标注(?:项目)?"
)
_EN_SETUP = re.compile(
    r"\b(?:set up|create|start|build|make)\b.{0,40}?\b(?P<shape>box|bounding box|polygon|"
    r"classification|keypoint)?\s*(?:annotation|labell?ing)\b(?:\s+project)?"
    r"(?:\s+(?:for|of)\s+(?P<labels>[a-z ,/&-]{2,60}?))?"
    r"(?=[.;]|,\s*(?:with|and|packages?|then|cross|two)\b|\s+(?:with|in|on|using)\b|$)",
    re.IGNORECASE,
)
_ZH_REASSIGN = re.compile(
    r"把(?P<holder>[^\uff0c。,\s]{1,20}?)(?:手里|手上|名下|那里|那儿)的?"
    r"(?P<untouched>没动|未动|没开始|未开始|还没动|没有动|没碰)?(?:过)?的?任务"
    r"(?:都|全部)?(?:分|派|转|交|改派)(?:给)?(?P<target>[^\uff0c。,.\s]{1,20})"
)
_EN_REASSIGN = re.compile(
    r"\b(?:reassign|move|give|hand|transfer)\s+(?P<holder>[\w.-]+?)'s\s+"
    r"(?P<untouched>untouched|unstarted|idle|unopened|not started)?\s*tasks?\s+to\s+"
    r"(?P<target>[\w.-]+)",
    re.IGNORECASE,
)
_DRAFT = re.compile(
    r"(?:起草|草拟|拟一份|拟个|先拟|draft)(?P<topic>.{0,40}?)"
    r"(?:标签集|标签|label set|labels?|指南|guidelines?)",
    re.IGNORECASE,
)
_SPLIT = re.compile(r"[、,\uff0c/和与及&]|\band\b", re.IGNORECASE)
_TEAM = re.compile(
    r"交叉|互审|标审分离|两人|双人|cross[- ]?check|cross[- ]?review|two people", re.IGNORECASE
)
_GROUP = re.compile(r"小组|审核|review", re.IGNORECASE)
_SAMPLE = re.compile(
    r"(?:抽|抄|抽检|sample|inspect)\s*(?P<rate>\d{1,2})\s*%|"
    r"(?P<after>\d{1,2})\s*%\s*(?:的)?(?:抽检|抽查|spot[- ]?check|sample|inspection)",
    re.IGNORECASE,
)
_PACKAGE = re.compile(
    r"每(?:包|个包)\s*(?P<a>\d{1,5})|每\s*(?P<b>\d{1,5})\s*(?:张|条|个)(?:一|切一|为一)?包|"
    r"packages? of (?P<c>\d{1,5})|(?P<d>\d{1,5}) (?:per|each) package",
    re.IGNORECASE,
)


def _labels(raw: str) -> list[str]:
    cleaned = re.sub(r"^(?:的|给|一份|个)|(?:的)$", "", raw.strip())
    return [part.strip() for part in _SPLIT.split(cleaned) if part.strip()][:20]


def _slug(name: str, index: int) -> str:
    ascii_name = re.sub(r"[^a-z0-9]+", "_", name.casefold()).strip("_")
    return ascii_name or f"label_{index + 1}"


def _tier(text: str) -> str:
    if _TEAM.search(text):
        return "team"
    return "group" if _GROUP.search(text) else "personal"


def _package_size(text: str) -> int | None:
    match = _PACKAGE.search(text)
    if match is None:
        return None
    return int(next(value for value in match.groupdict().values() if value))


def _project_notes(text: str, language: str, tier: str) -> tuple[str, list[str]]:
    """Project guidelines for spot checks, and readable notes for what the steps imply."""
    notes: list[str] = []
    guidelines = ""
    sampled = _SAMPLE.search(text)
    if sampled:
        rate = sampled.group("rate") or sampled.group("after")
        guidelines = (
            f"每个任务包验收时抽检 {rate}% (accept_package) 。"
            if language == "zh"
            else f"Each package is accepted by inspecting a {rate}% sample (accept_package)."
        )
        notes.append(guidelines)
    if tier == "team":
        notes.append(
            "两人交叉: 项目用团队流程, 每个任务都由另一人复核。"
            if language == "zh"
            else "Two people cross-check: the team workflow adds a second reviewer to every task."
        )
    return guidelines, notes


def setup_project(text: str) -> IntentDraft | None:
    """Label set, publication, project and packages for a new annotation job."""
    match = _ZH_SETUP.search(text) or _EN_SETUP.search(text)
    if match is None or "起草" in text or re.search(r"\bdraft\b", text, re.IGNORECASE):
        return None
    labels = _labels(match.group("labels") or "")
    if not labels:
        return None
    language = language_of(text)
    shape = match.group("shape") or ""
    name = (
        ("".join(labels) + (shape or "") + "标注")
        if language == "zh"
        else (" ".join(labels).title() + " annotation")
    )
    tier = _tier(text)
    guidelines, notes = _project_notes(text, language, tier)
    project: dict[str, JsonValue] = {
        "name": name,
        "label_set_id": {"$ref": "s1.label_set_id"},
        "label_set_version": {"$ref": "s1.label_set_version"},
        "workflow_tier": tier,
        "guidelines": guidelines,
    }
    split: dict[str, JsonValue] = {"project_id": {"$ref": "s3.project_id"}}
    size = _package_size(text)
    if size:
        split["package_size"] = size
    label_values: list[JsonValue] = [
        {"id": _slug(label, index), "name": label} for index, label in enumerate(labels)
    ]
    steps = [
        DraftStep(
            id="s1", action="create_label_set", params={"name": name, "labels": label_values}
        ),
        DraftStep(
            id="s2",
            action="publish_label_set",
            params={
                "label_set_id": {"$ref": "s1.label_set_id"},
                "version": {"$ref": "s1.label_set_version"},
            },
        ),
        DraftStep(id="s3", action="create_project", params=project),
        DraftStep(id="s4", action="split_packages", params=split),
    ]
    return IntentDraft(kind="plan", steps=steps, notes=notes, language=language, confident=True)


def reassign_untouched(text: str) -> IntentDraft | None:
    """Take a holder's tasks back and assign the same tasks to another person."""
    match = _ZH_REASSIGN.search(text) or _EN_REASSIGN.search(text)
    if match is None:
        return None
    language = language_of(text)
    selector: dict[str, JsonValue] = {
        "holder": match.group("holder"),
        "untouched": bool(match.group("untouched")),
    }
    reason = (
        f"改派给 {match.group('target')}"
        if language == "zh"
        else f"Reassigned to {match.group('target')}"
    )
    steps = [
        DraftStep(
            id="s1",
            action="revoke_assignment",
            params={"task_id": {"$tasks": selector}, "reason": reason},
        ),
        DraftStep(
            id="s2",
            action="assign_tasks",
            params={
                "task_ids": {"$tasks": selector},
                "actor": match.group("target"),
                "strategy": "assign",
            },
        ),
    ]
    return IntentDraft(kind="plan", steps=steps, language=language, confident=True)


def draft_labels(text: str) -> IntentDraft | None:
    """One controlled drafting action; sources are filled from the page and the catalog."""
    match = _DRAFT.search(text)
    if match is None:
        return None
    topic = re.sub(r"^(?:一份|一个|个|份|a|an|the)\s*|(?:的|和|and)\s*$", "", match.group("topic"))
    topic = re.sub(r"^.*?(?:起草|草拟)", "", topic).strip(" ,\uff0c")
    language = language_of(text)
    name = topic or ("标签集草稿" if language == "zh" else "Draft labels")
    step = DraftStep(
        id="s1",
        action="draft_label_set",
        params={"name": name, "topic": topic, "language": language},
    )
    return IntentDraft(kind="plan", steps=[step], language=language, confident=True)


RECIPES: tuple[Callable[[str], IntentDraft | None], ...] = (
    draft_labels,
    reassign_untouched,
    setup_project,
)

RECIPE_GUIDE = (
    "Recipes: (1) a new annotation job = create_label_set (labels: the objects the person "
    "names, e.g. 红绿灯 for 红绿灯框标注; use draft_label_set only when the person asks for a "
    "draft or names a standard, annotations or sample files to draft from) -> "
    "publish_label_set (projects need a published version) -> create_project "
    "(label_set_id/label_set_version from s1, workflow_tier team when two people cross-check "
    "or annotators and reviewers must differ, a spot-check rate such as 抽 10%/10% sample goes "
    "into guidelines as '每个任务包验收时抽检 10%' or 'Each package is accepted by inspecting "
    "a 10% sample') -> split_packages (project_id from s3). (2) give X's untouched tasks to "
    "Y = revoke_assignment for each task "
    '({"$tasks": {"holder": "X", "untouched": true}} as task_id, reason required) -> '
    'assign_tasks (task_ids: the same $tasks selector, actor: Y, strategy: "assign"). '
    "(3) drafting labels or guidelines from a standard, annotations or sample files = "
    "draft_label_set."
)


def match_recipe(text: str) -> IntentDraft | None:
    """Return the first recipe whose wording matches the sentence."""
    for recipe in RECIPES:
        draft = recipe(text)
        if draft is not None:
            return draft
    return None


# Words that carry no object or parameter of their own once a recipe matched.
_FILLER = re.compile(
    r"请|帮我|帮忙|麻烦|一下|一份|一个|这批|这些|这个|这里|当前|按照|按|根据|参考|基于|给|把|"
    r"的|了|吧|呢|啊|和|与|及|并|然后|再|都|全部|所有|图片|照片|图像|图|张|项目|任务|数据集|"
    r"数据|标签集|标签|标注|指南|说明|规范|吧|"
    r"\b(?:please|kindly|for|these|this|the|a|an|on|in|of|to|with|and|then|it|them|all|"
    r"images?|pictures?|photos?|files?|dataset|data|project|tasks?|labels?|guidelines?|"
    r"annotations?|instructions?|from|using|based|current|here|me|us|can|you|could)\b",
    re.IGNORECASE,
)
_MEANING = re.compile(r"[一-鿿]{2,}|[a-z]{2,}|\d", re.IGNORECASE)


def _spans(text: str) -> list[tuple[int, int]]:
    """Consumed spans, each extended to the end of its last word ("cross-check" + "ing")."""
    patterns = (_ZH_SETUP, _EN_SETUP, _ZH_REASSIGN, _EN_REASSIGN, _DRAFT, _TEAM, _SAMPLE, _PACKAGE)
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            end = match.end()
            while end < len(text) and text[end].isascii() and text[end].isalnum():
                end += 1
            spans.append((match.start(), end))
    return spans


def recipe_covers(text: str) -> bool:
    """True when a recipe uses every object and value the sentence mentions.

    Whatever is left after removing what the recipes consumed and plain filler must carry
    no meaning (no name, number or word of its own); otherwise a model plans the sentence,
    because the recipe would silently ignore what it does not understand.
    """
    kept = list(text)
    for start, end in _spans(text):
        kept[start:end] = [" "] * (end - start)
    leftover = _FILLER.sub(" ", "".join(kept))
    return _MEANING.search(leftover) is None
