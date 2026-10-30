# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Plain English and Chinese wording for AI pre-review reasons.

Reviewers read these sentences, so they name objects the way a person counts them (box 2),
use label display names, and never show identifiers, Python reprs or statistics jargon. The
numeric detail stays in the rule code and weight; the object references keep the jump-to.
"""

from collections.abc import Mapping, Sequence

from datakeel.core.annotation_models import AnnotationRecord
from datakeel.core.prelabel_models import ObjectRef

_KINDS = {
    "box": ("Box", "框"),
    "polygon": ("Polygon", "多边形"),
    "span": ("Text span", "文本片段"),
}
_FINDING_TEXT: dict[str, tuple[str, str]] = {
    "invalid_bbox": (
        "{where} has no area or lies outside the image",
        "{where_zh}面积为零或超出了图片范围",
    ),
    "invalid_span": ("{where} is empty or outside the text", "{where_zh}为空或超出了文本范围"),
    "minority_label": (
        "Most other annotators chose different labels for this sample",
        "其他标注员给这条样本选的标签大多不同",
    ),
    "multilabel_conflict": (
        "The labels {labels} should not be used together under this project's template",
        "按项目模板的设置，{labels_zh}不应同时出现",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
    "bbox_category_minority": (
        "Other annotators gave {where} a different label",
        "其他标注员给{where_zh}标的是别的类别",
    ),
    "span_category_minority": (
        "Other annotators gave {where} a different label",
        "其他标注员给{where_zh}标的是别的类别",
    ),
    "bbox_size_outlier": (
        '{where} is far larger or smaller than other "{category}" boxes in this project',
        "{where_zh}比项目里其他「{category}」框大得多或小得多",
    ),
    "bbox_aspect_outlier": (
        '{where} is much wider or taller than other "{category}" boxes in this project',
        "{where_zh}的长宽比和项目里其他「{category}」框差别很大",
    ),
    "span_length_outlier": (
        '{where} is far longer or shorter than other "{category}" spans',
        "{where_zh}比其他「{category}」片段长得多或短得多",
    ),
    "bbox_missing": (
        "Other annotators drew a box that this annotation lacks",
        "其他标注员画了一个框，这条标注里没有",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
    "bbox_extra": ("Other annotators did not draw {where}", "其他标注员没有画{where_zh}"),
    "span_missing": (
        "Other annotators marked a text span that this annotation lacks",
        "其他标注员标了一个文本片段，这条标注里没有",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
    "span_extra": ("Other annotators did not mark {where}", "其他标注员没有标{where_zh}"),
    "duplicate_bbox": (
        "{where} almost exactly repeats another box",
        "{where_zh}和另一个框几乎重合，可能标重复了",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
    "duplicate_span": (
        "{where} almost exactly repeats another span",
        "{where_zh}和另一个片段几乎重合，可能标重复了",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
    "span_boundary_minority": (
        "Other annotators placed the edges of {where} differently",
        "其他标注员给{where_zh}划的边界不一样",
    ),
    "rare_category": (
        "{category_or_labels} is used only once in this project; check it was not a wrong pick",
        "{category_or_labels_zh}在整个项目里只出现一次，请检查是否选错",  # noqa: RUF001  # Chinese punctuation is intended.
    ),
}
_GENERIC = (
    "An automatic consistency check flagged this annotation",
    "自动一致性检查认为这条标注可疑",
)


def object_name(kind: str, index: int) -> tuple[str, str]:
    """Name one object as a reviewer counts it from one, in English and Chinese."""
    if kind == "label_set":
        return "The labels", "分类标签"
    english, chinese = _KINDS.get(kind, ("Object", "对象"))
    return f"{english} {index + 1}", f"第 {index + 1} 个{chinese}"


def label_names(labels: Sequence[str], names: Mapping[str, str]) -> tuple[str, str]:
    """Quote label display names for English and Chinese sentences."""
    shown = [names.get(label, label) for label in sorted(set(labels))]
    return ", ".join(f'"{label}"' for label in shown), "、".join(f"「{label}」" for label in shown)


def percent(value: float) -> str:
    """Show a confidence as a whole percentage."""
    return f"{round(value * 100)}%"


def _category(record: AnnotationRecord | None, reference: ObjectRef | None) -> str | None:
    if record is None or reference is None:
        return None
    shapes = {"box": record.boxes, "polygon": record.polygons, "span": record.spans}
    items = shapes.get(reference.kind) or ()
    return items[reference.index].category if reference.index < len(items) else None


def finding_text(
    code: str,
    objects: Sequence[ObjectRef],
    record: AnnotationRecord | None,
    names: Mapping[str, str],
) -> tuple[str, str]:
    """Word one P26 rule hit for reviewers, naming its first located object and label."""
    english, chinese = _FINDING_TEXT.get(code, _GENERIC)
    first = objects[0] if objects else None
    where, where_zh = (
        object_name(first.kind, first.index) if first else ("This annotation", "这条标注")
    )
    category = _category(record, first)
    shown = names.get(category, category) if category else None
    labels, labels_zh = label_names(record.labels or () if record else (), names)
    values = {
        "where": where,
        "where_zh": where_zh,
        "category": shown or "",
        "labels": labels,
        "labels_zh": labels_zh,
        "category_or_labels": f'"{shown}"' if shown else labels or "One label",
        "category_or_labels_zh": f"「{shown}」" if shown else labels_zh or "有个标签",
    }
    return english.format(**values), chinese.format(**values)
