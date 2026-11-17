# Backlog

## 已处理（v0.27.0）
- 意图路由扩充 `dataset-health`、`metric-change` 口语化双语概念同义词与英语不规则动词词形还原，并支持三槽位工作流在命中 `entity + outcome` 部分概念时进入 `intent_classifier` 分支（`eval-route` 116/116 意图与 14/14 档位 100% 通过）。
- 价目表 [`model-prices.yaml`](../contracts/model-prices.yaml) 补齐多档 OpenAI / Anthropic 模型单价，新增三档分档加同服务商备用示例 [`models-tiered.example.yaml`](../contracts/routing/models-tiered.example.yaml)，并核验百炼视觉转写（含 `auto` 模式）签批卡与运行报告的转写费用上限。
- 知识问句扩充「有谁在看/查/拉取」、断供宕机反事实及 `wind up`/`land in`/「落到」流向词表，并新增可选模型意图候选提议加确定性主语/焦点/候选项/方向规则核对（`K18-verified-model-candidate`）。
- 返工率只读函数 `rework_rate` 与一句话入口支持按 `today`、`this_week`、`last_week`、`this_month`、`last_7_days`、`last_30_days`、`days` 或显式 `since`/`until` UTC 时间窗口过滤审核记录。
- 图片数据集别名草稿（`kg.same_as`）统一采用图片抽取身份 `kg-image:`（与图片关系身份一致），图片抽图谱接口显式恢复 OpenAPI 422 `HTTPValidationError` 响应 schema。

## 已处理（v0.19.0–v0.26.0 已落地）
- 团队档 B8：任务列表显示序持久化为 `production_tasks.display_rank`，领取恢复单条 `ORDER BY … SKIP LOCKED` 查询；SQLite 走 schema v3 纯增量迁移，PostgreSQL 启动收敛索引，双栈复测全部达标（v0.26.0，证据见 [CAPACITY.md](CAPACITY.md)）。
- 目录对象、指标、维度与术语支持可选 `english_name`；负责人英文展示名单独登记在 [`owners.yaml`](../contracts/semantic-layer/owners.yaml)，英文界面优先使用并在缺省时回退原名。
- 对象短 ID（`shortId`）仅对完整 UUID 截取前 8 位展示，`retail_revenue` 等业务文本 ID 完整保留，复制始终使用完整身份。
- 语义层 [`metrics.yaml`](../contracts/semantic-layer/metrics.yaml) 补齐常用指标英文名称与单复数同义词，问数解析支持规范化标识符词形匹配。
- 图片知识图谱转写支持 `auto` 模式：本地 OCR 打底，按置信度与结构特征信号决定是否回退视觉模型。

## 已处理（2026-10-30，v0.18.0）
- 导入目录时记下每个文件在目录里的相对路径，工作台悬停显示、按目录名能搜到，不同目录下的同名文件分得开；绝对路径不返回。单独导入的文件和之前导入的老数据集仍显示文件名。
- 标签名小牌限宽加省略号、悬停显示全名，放大时留在可见画布里；小牌不接鼠标，不挡画框、加点和选中。

## 已处理（2026-10-23）
- 流水线终态写 `finished_at`，运行记录显示真实耗时；旧库自动补列，旧任务保持未知耗时。
- 指标详情标题与关系图复用同一双语名称。
- `update_metric` 在 prepare 阶段逐条拒绝缺失的目录引用；YAML 导入仍登记 unresolved。
- 未审批、审批拒绝与审批已消费的 execute 统一记 `DENIED`，公开具体 `reason`。
- `cli/evidence_benchmark.py` 补充命令入口及失败清理回归，纳入 ≥90% 模块覆盖率门禁。
- 运行时许可审计覆盖锁定 Python 闭包和实际前端产物；MIT-0、CC0-1.0、MIT-CMU 已纳入通用白名单，未知或未批准许可继续阻断门禁。
- 公开导出清理全部保留历史中的内部背景引用，排除内部过程文档，统一作者与提交者身份并独立扫描验证；支持保留历史与单提交快照。
- 公开版已完成全新克隆、独立依赖安装与 SQLite 完整门禁验证。
- 中英十分钟导览与脚本直接生成的截图齐全，覆盖证据审阅、版本、审批、回执、目录、问数、指标回滚和快捷搜索。
- 公开内容扫描放行保留域邮箱，样例使用 `example.org`；工作树扫描纳入 `make check`，检查已跟踪修改和未忽略的新文件。
- 英文对象标题、面包屑、快捷搜索和签批对象名与图卡片复用同一目录名称翻译，未知名称回退原名，中文和非目录对象保持原有行为。

- 安全问题与行为准则举报统一走 GitHub 私密报告。

## 后续

当前无待处理长尾积压项。
