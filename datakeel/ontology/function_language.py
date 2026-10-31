# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bilingual phrases and examples for every read-only function.

Same format as action language: (Chinese phrase, English phrase, Chinese example,
English example). The one-sentence entry reads these only through the ontology registry.
"""

FUNCTION_LANGUAGE: dict[str, tuple[str, str, str, str]] = {
    "project_progress": (
        "项目进度",
        "project progress",
        "这个项目现在标完多少了, 各状态各几条",
        "How far along is this project, by task state?",
    ),
    "package_status": (
        "任务包进度",
        "package status",
        "第 3 个任务包还剩多少没标",
        "How many tasks are left in package 3?",
    ),
    "annotator_workload": (
        "标注员工作量",
        "annotator workload",
        "每个标注员手上各有多少条、完成了多少",
        "How many tasks has each annotator been assigned and completed?",
    ),
    "rework_rate": (
        "返工率",
        "rework rate",
        "这周谁的返工率最高",
        "Who has the highest rework rate this week?",
    ),
    "annotation_consistency": (
        "标注一致性",
        "annotation consistency",
        "这个项目几个人标得一致吗",
        "How consistent are the annotators on this project?",
    ),
    "prelabel_confidence": (
        "预标注置信度分布",
        "prelabel confidence",
        "预标注的置信度都分布在哪些区间",
        "How are the prelabel confidence scores distributed?",
    ),
    "production_prelabel_accuracy": (
        "预标注准确率",
        "prelabel accuracy",
        "模型预标注和人工通过的结果对上了多少",
        "How often do model prelabels match the approved human labels?",
    ),
    "label_set_diff": (
        "标签集版本差异",
        "label set diff",
        "标签集第一版和第二版差了哪些标签",
        "Which labels changed between label set versions 1 and 2?",
    ),
    "next_task": (
        "下一条待标任务",
        "next task",
        "我下一条该标哪个任务",
        "Which task should I annotate next?",
    ),
    "production_objects": (
        "查生产对象",
        "production objects",
        "这个项目有哪些任务包",
        "Which task packages does this project have?",
    ),
    "lease_status": (
        "租约状态",
        "lease status",
        "哪些任务的租约快到期了",
        "Which task leases are about to expire?",
    ),
    "assignees": (
        "可派的人",
        "assignees",
        "这个项目的标注任务现在能派给谁",
        "Who can I assign this project's annotation tasks to?",
    ),
    "skill_workload": (
        "按技能看工作量",
        "skill workload",
        "按技能看, 每个人手上各有多少活",
        "What is each person's workload by skill?",
    ),
    "package_acceptance": (
        "任务包验收状态",
        "package acceptance",
        "这个任务包抽检验收过了吗",
        "Has this package passed sampling acceptance?",
    ),
    "list_datasets": (
        "列出数据集",
        "list datasets",
        "现在有哪些数据集",
        "Which datasets do we have?",
    ),
    "search_files": (
        "搜索文件",
        "search files",
        "这个数据集里质量低于 60 的文本有哪些",
        "Which text files in this dataset have quality below 60?",
    ),
    "get_quality": (
        "数据集质量",
        "dataset quality",
        "这个数据集的质量分是多少",
        "What is the quality score of this dataset?",
    ),
    "get_lineage": (
        "查血缘",
        "lineage",
        "这个数据集的上游是哪些",
        "What are the upstream sources of this dataset?",
    ),
    "get_report": (
        "治理报告",
        "governance report",
        "给我看看这个数据集的治理报告",
        "Show me the governance report for this dataset",
    ),
    "get_task": (
        "处理任务状态",
        "processing task status",
        "刚才那个处理任务跑完了吗",
        "Has the processing task finished?",
    ),
    "query_evidence": (
        "查证据",
        "query evidence",
        "哪些图片里有夜景",
        "Which images contain night scenes?",
    ),
    "get_evidence": (
        "样本证据",
        "sample evidence",
        "这张图片有哪些证据断言",
        "What evidence assertions does this image have?",
    ),
    "explain_sample": (
        "解释样本",
        "explain sample",
        "这条样本为什么被判成低质量",
        "Why was this sample flagged as low quality?",
    ),
    "ask_data": (
        "问数",
        "ask data",
        "上个月华东区的出货额是多少",
        "What was East China's shipment value last month?",
    ),
    "list_metrics": (
        "列出指标",
        "list metrics",
        "现在有哪些和出货相关的指标",
        "Which shipment-related metrics do we have?",
    ),
    "explain_metric": (
        "解释指标口径",
        "explain metric",
        "毛利率这个指标是怎么算的",
        "How is the gross margin metric calculated?",
    ),
    "impact_of": (
        "影响分析",
        "impact analysis",
        "改订单表会影响哪些下游指标",
        "Which downstream metrics depend on the orders table?",
    ),
    "query_kg": (
        "查知识图谱",
        "query knowledge graph",
        "图谱里周岩负责哪些系统",
        "Which systems does Zhou Yan own in the graph?",
    ),
    "explain_relation": (
        "解释图谱关系",
        "explain relation",
        "供应链数据组和运营中心是什么关系, 出处在哪",
        "How are the supply chain team and operations center related, and where is it stated?",
    ),
    "query_standard_coverage": (
        "数据标准覆盖率",
        "standard coverage",
        "订单表有多少列已经对上了数据标准",
        "How many columns in the orders table map to a standard?",
    ),
    "list_standard_usage": (
        "数据标准使用情况",
        "standard usage",
        "客户编号标准被哪些列用了",
        "Which columns use the customer ID standard?",
    ),
    "list_quality_rules": (
        "列出质量规则",
        "list quality rules",
        "订单表现在有哪些没通过的质量规则",
        "Which quality rules are failing on the orders table?",
    ),
    "get_table_quality": (
        "表质量分",
        "table quality",
        "订单表最近的质量分和规则历史怎么样",
        "What is the orders table's latest quality score and rule history?",
    ),
    "annotation_quality": (
        "标注质量评估",
        "annotation quality",
        "这个版本的标注质量怎么样, 几个人标得一致吗",
        "How good are the annotations in this version, and do annotators agree?",
    ),
    "training_distribution": (
        "训练集划分分布",
        "training split distribution",
        "按 8:1:1 划分后各类别分布均匀吗",
        "Is the class distribution balanced across an 80/10/10 split?",
    ),
    "training_leakage": (
        "训练集泄漏检查",
        "training leakage",
        "按目录划分的话训练集和测试集有重复图吗",
        "Would a directory split leak duplicate images between train and test?",
    ),
    "get_training_quality": (
        "训练数据体检结果",
        "training data quality",
        "这批训练文本的体检结果怎么样",
        "What did the training data quality check find?",
    ),
}


def function_language(name: str) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Return phrases and examples for one read function in both languages."""
    value = FUNCTION_LANGUAGE.get(name)
    if value is None:
        return {}, {}
    zh, en, example_zh, example_en = value
    return {"zh": [zh], "en": [en]}, {"zh": [example_zh], "en": [example_en]}
