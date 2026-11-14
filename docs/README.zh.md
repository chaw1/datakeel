# Datakeel 文档中心

[English](README.md) · [返回首页](../README.zh.md) · [十分钟导览](DEMO.md) · [接口参考](API_REFERENCE.zh.md)

本索引按使用场景整理 Datakeel 的操作导览、契约参考、部署配方与工程规范文档。

## 1. 快速上手

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [十分钟导览](DEMO.md) | 离线贯通工作台、证据校样、问数、工作流、知识图谱、沙箱算子与发布交付的端到端体验 | [ZH](DEMO.md) · [EN](DEMO.en.md) |
| [HTTP API 与流水线参考](API_REFERENCE.zh.md) | 接口汇总表、任务分片与去重、ObjectSet 1.1 查询、指标 YAML 合同、五维质量权重与 Trace 导出 | [ZH](API_REFERENCE.zh.md) · [EN](API_REFERENCE.md) |

## 2. 多模态证据、媒体质量与知识图谱

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [图片与点云质量](MEDIA_QUALITY.md) | 五项图片可用性评分、PLY/PCD 清洗与降采样、离群点过滤及俯视预览 | EN / ZH |
| [音视频预处理](MEDIA.md) | 基于本机 `ffmpeg`/`ffprobe` 的录音录像切片、合成演示与原始时间区间血缘 | EN / ZH |
| [文本与图片知识图谱](KG.md) | 实体提及定位、跨块关系归并、图片 OCR/视觉路由、目录关联与外发签批 | EN / ZH |
| [离线向量内核（Fake）](VECTOR_FAKE.md) | 离线向量 DAG 节点（`evidence.vector_embed`、语义去重/聚类/离群/缺口）与只读查询 | EN |
| [离线向量评测](VECTOR_OFFLINE_EVALUATION.md) | 仅开发态使用的 FAISS 精确对照实验与冷/热/增量合成基准评测 | EN / ZH |
| [自定义算子](CUSTOM_OPERATORS.md) | 单文件 Python 算子提交、源码静态审查、SHA-256 签批与容器沙箱执行 | EN / ZH |
| [近重复 Rust 加速](RUST_ACCEL.md) | 可选 `datakeel-accel` 扩展（`DATAKEEL_ACCEL=auto\|off\|required`）加速 64 位 dHash 与训练文本指纹 | EN / ZH |

## 3. 标注生产、训练集与发布交付

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [数据生产流程](PRODUCTION.zh.md) | 标签集发布、只追加修订、小组/团队派单、审核返工与定稿到标准数据集版本 | [ZH](PRODUCTION.zh.md) · [EN](PRODUCTION.md) |
| [标注工作台](ANNOTATION_WORKBENCH.zh.md) | 快捷键标注、EXIF 摆正、模板属性表单、离线草稿与团队档项目驾驶舱 | [ZH](ANNOTATION_WORKBENCH.zh.md) · [EN](ANNOTATION_WORKBENCH.md) |
| [标注质量评估](ANNOTATION_QA.md) | 分类、二维框与文本片段标注的离线一致性指标与抽检验收 | EN / ZH |
| [训练集切分与导出](TRAINING.zh.md) | 固定种子分层切分、精确/SimHash/dHash/组键泄漏检查，以及 COCO/YOLO/HF/JSONL 可复现导出 | [ZH](TRAINING.zh.md) · [EN](TRAINING.md) |
| [大模型训练数据治理](LLM_DATA.zh.md) | SFT/指令/偏好对 JSONL 的试运行检查（结构、语言、去重、PII/密钥、评测集污染）与受控清洗 | [ZH](LLM_DATA.zh.md) · [EN](LLM_DATA.md) |
| [数据集说明书](DATASHEETS.md) | 强制逐句引用平台事实的七章说明书，支持 Markdown 与 HTML 下载 | EN / ZH |
| [数据集版本对比与交付](RELEASES.zh.md) | 版本差分、不可变发布、可复现 tar/目录交付包及 `datakeel reconcile` 离线对账 | [ZH](RELEASES.zh.md) · [EN](RELEASES.md) |

## 4. 企业目录、可追溯问数与数据治理

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [问数图表与多轮追问](ASK.zh.md) | 确定性图表选择、多轮追问解析、双语时间窗识别与拒答护栏 | [ZH](ASK.zh.md) · [EN](ASK.md) |
| [外部工程元数据导入](METADATA_IMPORTS.md) | 本地 dbt 产物、Airflow REST v1、鉴权 OpenLineage RunEvent 导入与指标草稿确认 | [ZH](METADATA_IMPORTS.md) · [EN](METADATA_IMPORTS.en.md) |
| [数据标准与落标检查](STANDARDS.md) | 可移植字段标准、双语码表、规则映射建议与落标覆盖率 | EN / ZH |
| [数据质量规则](QUALITY_RULES.md) | SQLite/PostgreSQL 表契约监控、worker 定时巡检、问题单指派与签名告警 | EN / ZH |
| [数据资产上架与使用](DATA_ASSETS.md) | 公开/内部/需申请/受限分级、授权申请签批，以及查询/导出/下载独立作用域 | [ZH](DATA_ASSETS.md) · [EN](DATA_ASSETS.en.md) |
| [表格与时序剖析](TIMESERIES.md) | 本地 CSV/TSV 剖析、确定性异常规则与受控目录剖析 | EN / ZH |

## 5. 受控动作、智能体、工作流与权限

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [受控动作结果](ACTIONS.md) | 冻结计划摘要、有效期、可逆性标识、一次性审批以及恢复暂停的 Agent 断点 | EN / ZH |
| [确定性工作流](WORKFLOWS.md) | YAML 工作流合同、CLI/HTTP/SSE 执行、意图路由校验与审批暂停恢复 | EN / ZH |
| [委派与记忆](AGENT.md) | 嵌套只读子 Agent、不可信工具信封、canary 泄漏拦截、跨会话记忆与持久预算 | EN / ZH |
| [一句话做事（试用）](ONE_SENTENCE.zh.md) | 自然语言多步动作链规划、缺参追问与确认前零改动保证 | [ZH](ONE_SENTENCE.zh.md) · [EN](ONE_SENTENCE.md) |
| [身份与 HTTP 访问](IDENTITY_ACCESS.zh.md) | 操作人登记、角色绑定、动作权限解析与零用户本地模式 | [ZH](IDENTITY_ACCESS.zh.md) · [EN](IDENTITY_ACCESS.md) |

## 6. 架构、部署与运维

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [架构决策](ARCHITECTURE.md) | 模块化单体、`api`/`worker` 双进程、SQLite/PostgreSQL 事实源、S3/本地存储与分层依赖 | ZH |
| [持久化 Schema 组合](PERSISTENCE_SCHEMA.md) | Schema 基线归属、SQLite 版本化升级与 PostgreSQL 迁移对齐 | EN |
| [小团队部署指南](DEPLOYMENT.zh.md) | 回环服务配合 Caddy / nginx + oauth2-proxy 认证代理、Compose 编排与六项安全验收清单 | [ZH](DEPLOYMENT.zh.md) · [EN](DEPLOYMENT.md) |
| [SQLite 数据库维护](DATABASE_MAINTENANCE.md) | `db status`/`db upgrade` 显式升级流程、维护锁与哈希校验本地恢复包 | EN |
| [容量与规模压测](CAPACITY.md) | 可复现 S/M/L 规模负载、双栈基准测量结果与团队档 B8 抢单复测证据 | EN / ZH |

## 7. 工程规范、评测验证与社区协作

| 文档 | 说明 | 语言 |
| --- | --- | --- |
| [代码规范与工具门禁](CODE_STANDARDS.md) | 格式化、Ruff ALL、严格 Pyright、`import-linter`、文件与函数规模上限、覆盖率及许可策略 | ZH |
| [离线评测与完整门禁](VERIFICATION.zh.md) | 58 条 golden、856 个变异锚点、`eval-evidence`/`eval-ask`、截图矩阵与 `make check` | [ZH](VERIFICATION.zh.md) · [EN](VERIFICATION.md) |
| [测试执行提速](TEST_SPEED.md) | worker 并行调度、PostgreSQL 模板克隆与 CI 分片汇总机制 | EN / ZH |
| [公开仓库导出](PUBLIC_EXPORT.md) | 历史/快照清理导出流程、公开内容扫描规则与全新克隆校验 | EN / ZH |
| [界面设计「校样 · 出处档案」](design/UI-DIRECTION-B.md) | 校样工作台与三套验证对比度色板的设计规范 | ZH |
| [待办清单（Backlog）](BACKLOG.md) | 已完成里程碑记录与后续工程改进项 | ZH |
| [合同说明](../contracts/README.md) | 语义层与文件格式合同、算子清单生成及漂移检查 | EN |
| [贡献指南](../CONTRIBUTING.md) · [支持与提问](../SUPPORT.md) · [安全说明](../SECURITY.md) · [更新日志](../CHANGELOG.md) | 本地开发搭建、提问渠道、私密漏洞报告与版本更新记录 | EN / ZH |
