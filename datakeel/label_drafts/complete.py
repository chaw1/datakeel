# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Make every drafted label complete and state truthfully where its examples came from."""

import re
from dataclasses import dataclass, field

from datakeel.core.label_guidelines import GuidelineExample, LabelGuideline, LabelGuidelines
from datakeel.core.production_attributes import TemplateAttribute
from datakeel.core.production_catalog_models import ProductionLabel
from datakeel.label_drafts.models import DraftInputs, DraftOutcome
from datakeel.label_drafts.offline import build_labels, offline_rule

# Lets annotators flag a case they cannot decide when no source defines any attribute.
UNCERTAIN = TemplateAttribute(
    key="uncertain", name_zh="不确定", name_en="Uncertain", type="boolean"
)
_END = "\u3002.!?\uff01\uff1f"
_EXAMPLE_TALK = re.compile(
    rf"[^{_END}]*(正例|反例|正反例|examples?\b)[^{_END}]*[{_END}]?", re.IGNORECASE
)


@dataclass
class Provenance:
    """Counts behind the overview's statement of where names, attributes and examples came from."""

    annotated: int = 0
    judged: int = 0
    described: int = 0
    placeholder_names: list[str] = field(default_factory=list[str])
    default_attributes: int = 0


def completed_labels(labels: list[ProductionLabel], found: Provenance) -> list[ProductionLabel]:
    """Both names and at least one attribute on every label, noting each stand-in used."""
    completed: list[ProductionLabel] = []
    for label in labels:
        name_zh = label.name_zh or label.name
        name_en = label.name_en or (name_zh if name_zh.isascii() else "")
        if not name_en:
            found.placeholder_names.append(name_zh)
        if not label.fields:
            found.default_attributes += 1
        completed.append(
            label.model_copy(
                update={
                    "name_zh": name_zh,
                    "name_en": name_en or name_zh,
                    "fields": label.fields or (UNCERTAIN,),
                }
            )
        )
    return completed


def _others(label: ProductionLabel, labels: list[ProductionLabel]) -> list[ProductionLabel]:
    return [item for item in labels if item.parent_id == label.parent_id and item.id != label.id][
        :3
    ]


def _described(label: ProductionLabel, labels: list[ProductionLabel], kind: str) -> tuple[str, str]:
    zh, en = label.name_zh or label.name, label.name_en or label.name
    if kind == "positive":
        return (
            f"正例(文字说明): 能明确认出是「{zh}」的对象, 标为本标签。",
            f"Positive (described): anything clearly recognisable as {en} gets this label.",
        )
    others = _others(label, labels)
    if others:
        names_zh = "、".join(f"「{item.name_zh or item.name}」" for item in others)
        names_en = ", ".join(item.name_en or item.name for item in others)
        return (
            f"反例(文字说明): {names_zh}不是「{zh}」, 不要标成本标签。",
            f"Negative (described): {names_en} are not {en}; do not give them this label.",
        )
    return (
        f"反例(文字说明): 看不清、无法确认是「{zh}」的对象不要标成本标签。",
        f"Negative (described): do not give this label to anything you cannot confirm is {en}.",
    )


def _complete_rule(
    rule: LabelGuideline,
    label: ProductionLabel,
    labels: list[ProductionLabel],
    annotated: tuple[GuidelineExample, ...],
    found: Provenance,
    labelled: frozenset[str] = frozenset(),
) -> LabelGuideline:
    kinds = {example.kind for example in rule.examples}
    extra = tuple(item for item in annotated if item.kind not in kinds)
    # A cited sample that already carries annotations came from them, not from sampled files.
    existing = sum(example.sample_id in labelled for example in rule.examples)
    found.judged += len(rule.examples) - existing
    found.annotated += len(extra) + existing
    text_zh, text_en = rule.text_zh, rule.text_en
    for kind in ("positive", "negative"):
        if kind in kinds or any(item.kind == kind for item in extra):
            continue
        found.described += 1
        added_zh, added_en = _described(label, labels, kind)
        text_zh, text_en = f"{text_zh}\n{added_zh}".strip(), f"{text_en}\n{added_en}".strip()
    return rule.model_copy(
        update={
            "text_zh": text_zh[:4000],
            "text_en": text_en[:4000],
            "examples": rule.examples + extra,
        }
    )


def completed_rules(
    labels: list[ProductionLabel],
    written: dict[str, LabelGuideline],
    inputs: DraftInputs,
    found: Provenance,
) -> tuple[LabelGuideline, ...]:
    """Every label gets a rule with a positive and a negative example, cited or described."""
    completed: list[LabelGuideline] = []
    labelled = frozenset(sample.id for sample in inputs.samples if sample.labels)
    for label in labels:
        fallback = offline_rule(label, inputs)
        rule = written.get(label.id)
        base = (
            fallback.model_copy(update={"examples": ()})
            if rule is None
            else rule.model_copy(
                update={
                    "text_zh": rule.text_zh or fallback.text_zh,
                    "text_en": rule.text_en or fallback.text_en,
                }
            )
        )
        completed.append(_complete_rule(base, label, labels, fallback.examples, found, labelled))
    return tuple(completed)


def _parts_zh(found: Provenance) -> list[str]:
    counts = (
        (found.annotated, "引用已有标注的样本 {} 条"),
        (found.judged, "模型看过抽样文件后挑选 {} 条"),
        (found.described, "没有可引用的样本、写成文字说明 {} 处"),
    )
    return [template.format(count) for count, template in counts if count]


def _parts_en(found: Provenance) -> list[str]:
    counts = (
        (found.annotated, "{} cite samples that already carry annotations"),
        (found.judged, "{} were picked by the model from the sampled files it saw"),
        (found.described, "{} are written descriptions where no sample could be cited"),
    )
    return [template.format(count) for count, template in counts if count]


def statement(found: Provenance) -> tuple[str, str]:
    """Where the examples, English names and attributes of this draft really came from."""
    zh = f"正反例来源: {'; '.join(_parts_zh(found))}。"
    en = f"Example sources: {'; '.join(_parts_en(found))}."
    if found.placeholder_names:
        names = "、".join(found.placeholder_names[:5])
        zh += f"{len(found.placeholder_names)} 个标签({names})暂无英文名, 先用中文名占位。"
        en += (
            f" {len(found.placeholder_names)} labels have no English name yet; "
            "the Chinese one stands in."
        )
    if found.default_attributes:
        zh += f"{found.default_attributes} 个标签没有现成的属性, 先给了「不确定」标记。"
        en += (
            f" {found.default_attributes} labels had no attribute in the standards or "
            "annotations and got an Uncertain flag."
        )
    return zh, en


def overview(written_zh: str, written_en: str, found: Provenance) -> tuple[str, str]:
    """The written overview without its own claims about examples, then the true statement."""
    zh, en = statement(found)
    kept_zh = _EXAMPLE_TALK.sub("", written_zh).strip()
    kept_en = _EXAMPLE_TALK.sub("", written_en).strip()
    return f"{kept_zh}\n{zh}".strip()[:8000], f"{kept_en}\n{en}".strip()[:8000]


def offline_draft(inputs: DraftInputs) -> DraftOutcome:
    """Draft without any model: categories become labels, annotated samples become examples."""
    found = Provenance()
    labels = completed_labels(build_labels(inputs), found)
    rules = completed_rules(labels, {}, inputs, found)
    overview_zh, overview_en = overview(
        f"「{inputs.name}」标注指南草稿, 共 {len(labels)} 个标签, 请人工检查后再发布。",
        f"Draft guidelines for {inputs.name}: {len(labels)} labels; review before publishing.",
        found,
    )
    return DraftOutcome(
        labels=tuple(labels),
        guidelines=LabelGuidelines(overview_zh=overview_zh, overview_en=overview_en, rules=rules),
    )
