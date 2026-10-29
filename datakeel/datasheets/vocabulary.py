# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Fixed presentation vocabulary, never a list of guessed entity identities."""

from datakeel.core.datasheet_models import DatasheetChapter, DatasheetLanguage

_TITLES = {
    "motivation": ("动机", "Motivation"),
    "composition": ("构成", "Composition"),
    "collection": ("采集", "Collection"),
    "preprocessing": ("预处理、清洗与标注", "Preprocessing, cleaning and annotation"),
    "uses": ("用途", "Uses"),
    "distribution": ("分发", "Distribution"),
    "maintenance": ("维护", "Maintenance"),
}
FIELD_LABELS = {
    "training.records": ("训练记录数量", "Training record count"),
    "training.language_distribution": ("语言分布", "Language distribution"),
    "training.deduplication_rate": ("去重比例", "Deduplication ratio"),
    "training.pii_records": ("个人信息记录数量", "Personal information record count"),
    "training.contamination_rate": ("评测污染比例", "Evaluation contamination ratio"),
    "training.format_error_rate": ("格式错误比例", "Format error ratio"),
    "training.issue_counts": ("训练问题数量", "Training issue counts"),
    "training.rule_version": ("规则版本", "Rule version"),
    "dataset.name": ("数据集名称", "Dataset name"),
    "version.created_at": ("版本创建时间", "Version creation time"),
    "manifest.file_count": ("文件数量", "File count"),
    "manifest.modalities": ("数据模态", "Data modalities"),
    "manifest.total_bytes": ("总字节数", "Total bytes"),
    "manifest.filenames": ("文件名称", "File names"),
    "quality.total": ("质量总分", "Quality score"),
    "quality.grade": ("质量等级", "Quality grade"),
    "quality.dimensions": ("质量维度", "Quality dimensions"),
    "quality.issues": ("质量问题", "Quality issues"),
    "compliance.total": ("合规总分", "Compliance score"),
    "compliance.issues": ("合规问题", "Compliance issues"),
    "lineage.operator": ("处理算子", "Processing operator"),
    "lineage.run_state": ("处理状态", "Processing state"),
    "lineage.occurred_at": ("处理时间", "Processing time"),
    "assertions.count": ("证据断言数量", "Evidence assertion count"),
    "assertions.status_counts": ("证据审阅状态", "Evidence review counts"),
    "assertions.verification_counts": ("证据核对状态", "Evidence verification counts"),
    "assertions.predicate_counts": ("证据类别", "Evidence predicate counts"),
    "assertions.inactive_count": ("已失效证据断言数量", "Inactive evidence assertion count"),
    "decisions.review": ("审阅决定", "Review decision"),
    "decisions.action": ("审阅动作", "Review action"),
    "decisions.status": ("审阅状态", "Review state"),
    "decisions.actor": ("审阅人", "Reviewer"),
    "decisions.reason": ("审阅理由", "Review reason"),
    "kg.entities": ("图谱实体", "Graph entities"),
    "kg.relation_count": ("图谱关系数量", "Graph relation count"),
}
_METADATA_LABELS = {
    "description": ("数据集描述", "Dataset description"),
    "purpose": ("目的", "Purpose"),
    "motivation": ("动机", "Motivation"),
    "source": ("来源", "Source"),
    "collection_method": ("采集方法", "Collection method"),
    "collection_period": ("采集期间", "Collection period"),
    "collection_date": ("采集日期", "Collection date"),
    "consent": ("授权记录", "Consent record"),
    "intended_use": ("预期用途", "Intended use"),
    "intended_uses": ("预期用途", "Intended uses"),
    "use_cases": ("使用场景", "Use cases"),
    "limitations": ("限制", "Limitations"),
    "prohibited_uses": ("禁止用途", "Prohibited uses"),
    "license": ("许可", "License"),
    "citation": ("引用方式", "Citation"),
    "access": ("访问方式", "Access"),
    "distribution": ("分发方式", "Distribution"),
    "creator": ("创建人", "Creator"),
    "owner": ("负责人", "Owner"),
    "maintainer": ("维护人", "Maintainer"),
    "contact": ("联系信息", "Contact"),
    "update_frequency": ("更新频率", "Update frequency"),
    "retention": ("保留策略", "Retention"),
}
FIELD_LABELS.update({f"metadata.{key}": value for key, value in _METADATA_LABELS.items()})
# Measurement units and value kinds are shown to the model and accepted as words of their facts.
UNIT_LABELS = {
    "records": ("\u6761", "records"),
    "files": ("\u4e2a", "files"),
    "assertions": ("\u6761", "assertions"),
    "relations": ("\u6761", "relations"),
    "bytes": ("\u5b57\u8282", "bytes"),
    "points": ("\u5206", "points"),
    "seconds": ("\u79d2", "seconds"),
    "USD": ("\u7f8e\u5143", "USD"),
    "CNY": ("\u5143", "CNY"),
}
KIND_LABELS = {
    "ratio": ("\u6bd4\u4f8b", "ratio"),
    "percent": ("\u767e\u5206\u6bd4", "percent"),
    "date": ("\u65e5\u671f", "date"),
    "name": ("\u540d\u79f0", "name"),
    "status": ("\u72b6\u6001\u503c", "status"),
}

# Unknown content words are refused even when lowercase or sentence-initial. This closed
# grammar intentionally prefers deleting a plausible paraphrase to admitting an invented name.
ENGLISH_GRAMMAR = frozenset(
    word
    for line in (
        "a an the this that these those it its their they them there is are was were be",
        "been being has have had with without and or but of for from to by in on at as",
        "into through under over not no only also each all any other per can may must",
        "should will would could does do did dataset datasets data file files contains",
        "contain containing consists include includes including comprise comprises",
        "comprising count total bytes name names version created creation time date",
        "recorded record records platform available unavailable missing unknown collected",
        "collection source sources method period consent permission description motivation",
        "purpose preprocessing processing cleaning annotation used use uses intended",
        "prohibited limitations distribution distributed access license licensed citation",
        "maintenance maintained maintainer owner owned creator contact update frequency",
        "retention quality score grade dimensions issues issue evidence assertion",
        "assertions review reviewed reviewer verification verified state status counts",
        "action reason operator graph entities entity relation relations modalities",
        "modality text image images audio video document documents number size percentage",
        "percent reported reports consists generated generation contains snapshot import",
        "imported named marks marked accepted rejected pending candidate candidates",
        "completed failed status true false null none metadata according following",
        "following records shows show value values identified listed list responsibility",
        "responsible managed manage responsible person organization read write public",
        "private internal external local open restricted not applicable suitable supports",
        "called maintains support applies apply assigned designated responsible includes dataset's",
        "step steps type types format formats under using used via",
    )
    for word in line.split()
)
CHINESE_GRAMMAR = (
    "图片",
    "图像",
    "观测",
    "文本",
    "视频",
    "音频",
    "数据集",
    "数据",
    "文件",
    "数量",
    "共有",
    "包含",
    "包括",
    "构成",
    "记录",
    "平台",
    "中",
    "的",
    "为",
    "是",
    "由",
    "于",
    "在",
    "和",
    "与",
    "及",
    "或",
    "以及",
    "了",
    "有",
    "无",
    "没有",
    "这些",
    "该",
    "本",
    "此",
    "其",
    "名称",
    "版本",
    "创建",
    "时间",
    "日期",
    "采集",
    "来源",
    "方法",
    "期间",
    "授权",
    "描述",
    "动机",
    "目的",
    "预处理",
    "处理",
    "清洗",
    "标注",
    "用途",
    "用于",
    "使用",
    "预期",
    "禁止",
    "限制",
    "分发",
    "访问",
    "许可",
    "引用",
    "方式",
    "维护",
    "负责人",
    "创建人",
    "维护人",
    "联系",
    "信息",
    "更新",
    "频率",
    "保留",
    "策略",
    "质量",
    "总分",
    "等级",
    "维度",
    "问题",
    "证据",
    "断言",
    "审阅",
    "核对",
    "状态",
    "动作",
    "理由",
    "算子",
    "图谱",
    "实体",
    "关系",
    "模态",
    "字节",
    "总",
    "个",
    "份",
    "条",
    "张",
    "件",
    "名",
    "次",
    "人",
    "项",
    "已",
    "未",
    "完成",
    "失败",
    "候选",
    "接受",
    "拒绝",
    "存在",
    "可用",
    "不可用",
    "缺失",
    "未知",
    "根据",
    "显示",
    "列出",
    "导入",
    "生成",
    "快照",
    "负责",
    "管理",
    "组织",
    "适用",
    "不适用",
    "支持",
    "内部",
    "外部",
    "公开",
    "私有",
    "仅",
    "仅供",
    "大小",
    "经过",
    "进行",
    "采用",
    "步骤",
    "类型",
    "格式",
    "年",
    "月",
    "日",
    "号",
)


def chapter_title(key: DatasheetChapter, language: DatasheetLanguage) -> str:
    """Return the fixed localized chapter title."""
    return _TITLES[key][language == "en"]


def missing_text(language: DatasheetLanguage) -> str:
    """Disclose absent platform facts without fabricating an explanatory claim."""
    if language == "en":
        return "No record of this item exists in the platform."
    return "平台中没有这一项的记录。"


def unit_label(unit: str | None, language: DatasheetLanguage) -> str | None:
    """Localize a declared unit; unknown units are shown literally."""
    if unit is None:
        return None
    return UNIT_LABELS.get(unit, (unit, unit))[language == "en"]


def kind_label(kind: str, language: DatasheetLanguage) -> str | None:
    """Name value kinds whose literal form matters, such as ratios, dates and names."""
    labels = KIND_LABELS.get(kind)
    return None if labels is None else labels[language == "en"]


def field_label(field: str, language: DatasheetLanguage) -> str:
    """Localize known fact fields and preserve unknown source coordinates literally."""
    key = "manifest.filenames" if field.startswith("manifest.filenames.") else field
    labels = FIELD_LABELS.get(key, (field, field))
    return labels[language == "en"]
