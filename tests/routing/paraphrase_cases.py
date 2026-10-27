# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Paraphrased workflow requests and questions about workflows, grouped by failure category."""

# Category 1: phrasal verbs and reworded requests whose rule score used to be zero.
PHRASAL_REQUESTS = [
    ("Get rid of the junk samples in this dataset.", "low-quality-cleanup"),
    ("Weed out the garbage entries and check quality again.", "low-quality-cleanup"),
    ("Clear out all the substandard records from the dataset.", "low-quality-cleanup"),
    ("Could you throw away the corrupted files after quarantining them?", "low-quality-cleanup"),
    ("Please prune the noisy samples.", "low-quality-cleanup"),
    ("Scrub the broken images out of this dataset and re-score it.", "low-quality-cleanup"),
    ("I need you to eliminate the defective records from the training set.", "low-quality-cleanup"),
    ("Change how retail revenue is defined and compare the answers.", "metric-change"),
    ("Redefine the order count formula, then show me the old and new answers.", "metric-change"),
    ("Please tweak how refund amount is calculated and compare before and after.", "metric-change"),
    ("Give this dataset a once-over and report back.", "dataset-health"),
    ("Vet the new dataset end to end.", "dataset-health"),
    ("Run diagnostics on this dataset.", "dataset-health"),
    ("Go over the whole dataset and give me a verdict.", "dataset-health"),
    ("Sanity-check the whole dataset and give me a conclusion.", "dataset-health"),
]
# Category 2: the classifier was right but the narrow literal check rejected it.
COLLOQUIAL_REQUESTS = [
    ("把这批数据里的垃圾样本清掉。", "low-quality-cleanup"),
    ("把不达标的文件删干净, 删之前先隔离。", "low-quality-cleanup"),
    ("麻烦把劣质图片都干掉。", "low-quality-cleanup"),
    ("零售额的口径改一下, 然后重新问一遍对比结果。", "metric-change"),
    ("退款额口径动一下, 改完再问一遍。", "metric-change"),
    ("把度量换成标价金额再算一次。", "metric-change"),
    (
        "Switch the retail revenue measure to list amount and ask the question again.",
        "metric-change",
    ),
    ("Swap retail revenue to the list-amount measure, then rerun my question.", "metric-change"),
    ("帮我给这批数据过一遍, 看看能不能用。", "dataset-health"),
    ("对这份数据摸个底。", "dataset-health"),
]
# Category 3: pick-out-and-dispose phrasings on which a classifier used to abstain.
PICK_AND_DISPOSE_REQUESTS = [
    ("把低分的条目挑出来处理掉。", "low-quality-cleanup"),
    ("把有问题的样本筛掉, 再看看整体质量。", "low-quality-cleanup"),
    ("Pick out the failing samples and dispose of them.", "low-quality-cleanup"),
    ("低分样本全部剔除, 走完审批再复查。", "low-quality-cleanup"),
]
POSITIVE_REQUESTS = [*PHRASAL_REQUESTS, *COLLOQUIAL_REQUESTS, *PICK_AND_DISPOSE_REQUESTS]

# Category 4: questions about a workflow itself, many of which match every keyword.
WORKFLOW_QUESTIONS = [
    "清理低质样本需要审批吗?",
    "低质样本清理大概要多久?",
    "数据集体检会做哪些事情?",
    "指标口径变更需要谁来批?",
    "上次低质样本清理的结果怎么样?",
    "做一次数据集体检要不要先停掉其他任务?",
    "清理低质样本会不会删掉原文件?",
    "低质样本清理上次跑完了吗?",
    "Does the low-quality cleanup need approval?",
    "How long does a dataset health check take?",
    "Will the cleanup delete the original files?",
    "Who signs off on a metric definition change?",
    "What happened in the last dataset health check?",
    "Is the low-quality sample cleanup reversible?",
    "Do I need approval to clean up low-quality samples?",
    "Can the metric definition change be rolled back?",
    "Should I run a health check on this dataset?",
    "Could you tell me how long the low-quality file cleanup takes?",
]
NEAR_MISSES = [
    "Show me the junk samples in this dataset.",
    "List the files with poor quality scores.",
    "Don't get rid of the low-quality samples yet.",
    "Just quarantine the garbage files for now.",
    "把这个数据集的名称改一下。",
    "Change the metric's display name to Net Revenue.",
    "Update the retail revenue formula.",
    "把零售额口径改成按标价算。",
    "Compare this month's revenue with last month.",
    "Clean up my browser cache.",
    "清理一下缓存。",
    "Tell me which samples are low quality.",
    "如果把低质样本都删了, 质量分会变成多少?",
    "把指标口径的说明文档更新一下。",
    "Check the row count of this dataset.",
    "Run the dataset import again.",
    "Explain how the dataset health check scores quality.",
    "Quarantine the low-quality samples but keep all originals.",
    "Delete the selected junk file.",
    "Export the dataset health report as PDF.",
    "Count the defective records in this dataset.",
    "Rename the retail revenue metric to Net Retail.",
]
NEGATIVE_MESSAGES = [*WORKFLOW_QUESTIONS, *NEAR_MISSES]
