# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Permission scopes in words, for refusals a person reads.

The exact scope ids stay in ``missing_scopes`` (and the role screens); a Chinese refusal
says 「缺少「审核」权限」 because ids such as production:assign carry English choice words.
"""

SCOPE_WORDS = {
    "annotations:accept": ("接收标注", "accepting annotations"),
    "catalog:write": ("编辑目录", "editing the catalog"),
    "data-assets:approve": ("审批数据资产", "approving data assets"),
    "data-assets:write": ("编辑数据资产", "editing data assets"),
    "datasets:export": ("导出数据集", "exporting datasets"),
    "datasets:publish": ("发布数据集", "publishing datasets"),
    "datasets:write": ("修改数据集", "changing datasets"),
    "evidence:write": ("记录证据", "recording evidence"),
    "files:delete": ("删除文件", "deleting files"),
    "files:write": ("修改文件", "changing files"),
    "kg:extract": ("抽取知识图谱", "extracting knowledge graphs"),
    "metrics:write": ("编辑指标", "editing metrics"),
    "operators:submit": ("提交算子", "submitting operators"),
    "pipelines:run": ("运行流水线", "running pipelines"),
    "production:accept": ("验收", "accepting delivered work"),
    "production:annotate": ("标注", "annotating"),
    "production:assign": ("派单", "assigning tasks"),
    "production:claim": ("领取任务", "claiming tasks"),
    "production:finalize": ("定稿", "finalizing projects"),
    "production:manage": ("项目管理", "managing projects"),
    "production:models": ("管理模型", "managing models"),
    "production:review": ("审核", "reviewing"),
    "quality:run": ("运行质检", "running quality checks"),
    "quality:write": ("编辑质检规则", "editing quality rules"),
    "roles:manage": ("管理角色", "managing roles"),
    "skills:manage": ("管理技能", "managing skills"),
    "standards:write": ("编辑数据标准", "editing data standards"),
    "terms:write": ("编辑术语", "editing terms"),
    "users:manage": ("管理人员", "managing people"),
}


def scope_words(scopes: list[str], language: str) -> str:
    """「审核」、「派单」 in Chinese; "reviewing (production:review)" in English."""
    if language == "zh":
        return "、".join(f"「{SCOPE_WORDS.get(scope, ('', ''))[0] or '对应'}」" for scope in scopes)
    return ", ".join(
        f"{SCOPE_WORDS[scope][1]} ({scope})" if scope in SCOPE_WORDS else scope for scope in scopes
    )
