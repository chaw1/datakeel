# 离线评测、变异测试与完整门禁

[English](VERIFICATION.md) · [文档中心](README.zh.md) · [代码规范](CODE_STANDARDS.md) · [测试执行提速](TEST_SPEED.md) · [返回首页](../README.zh.md)

Datakeel 内置确定性离线评测集、变异测试框架、页面截图矩阵/UI 冒烟脚本，以及统一的 `make check` 全仓质量门禁。

## 离线评测命令

```bash
uv run datakeel eval --provider fake
uv run datakeel eval --provider fake --json
uv run datakeel eval-evidence
uv run datakeel eval-evidence --json
uv run datakeel eval-ask
uv run datakeel eval-ask --json
uv run datakeel eval-kg --json
uv run datakeel eval-kg --profile replay-flash --json
uv run datakeel eval-kg --suite image --json
uv run datakeel eval-route
uv run python scripts/mutate.py --output mutation-results.json
```

## Golden Agent 评测（`eval`）

内置 **58 条 golden 用例**通过脚本化回复驱动真实本机服务与隔离样例，离线运行不调用付费模型（仅显式指定 `--provider openai` 或 `--provider anthropic` 时发起真实请求）：

- **基础能力（12）**：查询、动作、审批、打转检测、token/USD 预算、跨轮指代与 dry-run 模式。
- **多模态证据（4）**：证据查询、未知状态解释、按查询结果生成版本和删除待审。
- **企业问数（4）**：正确作答、冲突澄清、不可答拒答与受控修改指标后答案变化。
- **高级 Agent（12）**：子 Agent 委派、canary 泄漏拦截、注入诱导审批拦截及跨会话记忆。
- **知识图谱（4）**：关系查询、缺失端点解释、重放以及外发签批（对话执行记录为 0）。
- **知识问数与图片转录（7）**：4 条知识问数（候选审阅标签、缺失目录资产、主体歧义、已拒绝断言）与 3 条图片转录证据边界用例。
- **治理、质量、标准、资产与训练集（8）**：1 条无授权资产引导、2 条标准落标/使用列、2 条表质量规则与问题单历史、1 条标注一致性与抽检验收、2 条训练集分布与跨切分泄漏、1 条大模型训练数据质量核对。
- **一句话做事（6）**：多步动作链确认前不改数据、缺项目追问补齐、越权点名拒绝、先查权限再追问参数、不接受的参数转追问而不静默丢弃、无对应动作时直白说明。

第二次运行 `eval` 会报告上次运行 ID 以及通过数、token 与成本变化；`--json` 输出完整结果，存在失败用例时返回非零退出码。

## 变异测试（`scripts/mutate.py`）

`scripts/mutate.py` 要求临时源码副本中的 **856 处变异**全部为 `KILLED`：

- **基础、证据、问数与运行时**：`unknown → absent` 旁路后被 `explain_sample` golden 捕获；近重复阈值 `+4` 由 `A–B (6) / B–C (6) / A–C (12)` 真实图像链测试杀死；企业问数候选 ID 边界与 `unanswerable` 禁止猜数；签批恢复授权与工具调用幂等。
- **工作流、路由、Agent、图谱、资产与标准**：工作流签批恢复授权、意图得分分差、图环检测、切换备用模型前结算失败尝试；canary、委派深度、工具越权、记忆硬删与每轮记忆增强去重；图谱端点核对、丢弃待复核候选、缓存模型身份、审阅标签、标识符拆分、知识问句路线与拒绝后关系清理；资产缺授权、到期、撤销、精确范围、工具缓存重放、来源清单、消息重放与版本来源校验；标准合规排序倒置与已确认映射丢弃。
- **v0.13.0–v0.14.0**：时序检测、发布与交付、自定义算子、图片路由与坐标、数据资产、指标草稿、质量规则、元数据导入、标注质量与说明书；压测门禁、选图、追问解析与 MCP 拒绝 `approve_plan` / `execute_plan`。
- **v0.15.0**：训练集切分、导出、泄漏与写入授权，大模型训练数据检查、脱敏、去重与清洗，生产角色、指派、修订与预测导入，标注工作台与小修锚点。
- **v0.16.0–v0.17.0**：团队档租约过期与边界、回收器只收一次并重读续租、领取与审核队列标审分离、技能等级过滤、整包退回、PostgreSQL 加锁顺序与按人串行计负载；模板属性校验、收回/派单冻结范围、实际租约到期时间、先搜后分页、路径脱敏、派单预览负载、进行中阶段租约以及审核队列屏蔽自己标过的任务。
- **v0.18.0**：脱敏凭证启发式规则（`secret`/`token`/`key`/`auth` 字符类别、全数字、首字母外大写、8 位下限、随机度、连字符词、4 位口令、前缀配置键、已打码占位、紧跟中文标点、括号区号与单空格电话序列），导入记录图片宽高与相对路径并跳过隐藏项，YOLO 缺宽高拒绝，COCO 未知图片，重开任务不涨轮次，指派资格与相对路径工作台样本名。
- **v0.19.0**：EXIF 八方向摆正映射与老数据集补读、工作台与预标注摆正像素、老修订/批次/切分摆正、YOLO/COCO 方向往返、导出摆正清单与证据抽取器升版作废；项目锁定模板与签批升级；在手负载与派单上限；返工点名转派；问数英文解读与拒答原因码；云端预标注预算、估价、重跑、失败清单与单项目并发锁；IoU 匹配、置信度分档与校准；直通责任归属、持有人草稿与放宽签批；AI 预审规则、抽检比例、按风险排序审核队列及触发人标审分离。
- **v0.20.0–v0.22.0**：一句话做事说法登记门禁、整句固定说法、写容器来源、先查权限再追问、动作前提、空计划、受保护任务排除、人话卡片与修补轮；动作链签批、续跑不重复、请求人/签批人绑定；起草标签集来源与费用上限；按所配接口路由模型；骨架三态校验、模板 ID 对齐与已用点删除保护、EXIF/COCO 拓扑/可见性/边界保护、纯骨架与混合空框指标排除；段整数强类型、源 probe 检查、原生导入、过滤前格式拒绝、WebVTT 未审保护与混合指标降级。

单个隔离测试子进程限时 300 秒（共享运行器下完整 golden 评测限时 900 秒）。首次超时会在新源码副本重跑一次，再次超时则判为环境失败并阻断门禁；超时与初始化失败均不计为成功杀死变异。

## 证据与问数基准评测（`eval-evidence` / `eval-ask`）

### `eval-evidence`

在隔离进程中新生成 1,000 个样本并运行生产抽取 DAG，评测 [contracts/evidence/questions.yaml](../contracts/evidence/questions.yaml) 中的 15 题（近重复 4、冲突 4、损坏 4、无标注 3）。结果写入 `eval_runs`（`provider=evidence`）并记录题集 SHA-256，临时样本随评测结束清理。

- **默认 `prefix` 模式（合成语料）**：宏平均 precision `0.336567 → 1.000000`，recall `0.933333 → 0.989542`；直接样本对 `48/52`（precision `1.0`，recall `0.923077`）；val→train `47/51`（recall `0.921569`）；`threshold_met=true`。
- **`--mode exact`（合成语料）**：直接样本对 `52/52`、val→train `51/51`（precision/recall 均为 `1.0`）；宏平均 precision/recall 均为 `1.0`。
- 上述数值仅反映当前合成数据与所声明 baseline 的实测结果，不代表真实数据上的泛化表现。

### `eval-ask`

新建隔离本机企业 SQLite 数据源，按参考时刻 `2026-10-01T00:00:00Z` 评测 [20 道指标题](../contracts/ask/questions.yaml)（14 可答 `ok-`、4 不可答 `ua-`、2 澄清 `cl-`，数值容差 0.5%）以及 **23 条知识/路线用例**的初始与审后两态。全程不调用模型、不计 token 或费用。`threshold_met` 要求指标门槛（至少答对 13/14、拒答 4/4、证据完整 20/20）与知识/路线两态全部通过。

## 全仓开发门禁与页面验收

执行完整开发门禁需要 Node.js 22 与 Rust 1.96 工具链：

```bash
uv run python scripts/generate_semantic.py
uv run pytest tests/semantic
(cd web && npm ci && npm run build)
make check
uv run python scripts/check_readme.py
bash scripts/ci-check.sh
```

- `make check` 依次执行 `check-public`、`check-rust`、`check-python`（格式、Ruff ALL、严格 Pyright、`import-linter`、`check_size.py`、`check_boundaries.py`、`check_schema`、`check_web_tests.py`、pytest 与 ≥85% 总覆盖率 / ≥90% 模块覆盖率）、`check-scale`、`check-web` 与 `check_licenses`。
- `bash scripts/ci-check.sh` 是本地 CI 等价入口，额外执行 `scripts/check_readme.py` 与 `scripts/mutate.py`。设置 `DATAKEEL_TEST_DATABASE_URL` 指向本机新建 PostgreSQL 库（需 `CREATEDB` 权限）可在 PG 栈重复验证；`DATAKEEL_TEST_WORKERS=1` 切换串行。CI 分片详情见 [TEST_SPEED.md](TEST_SPEED.md)。
- 对运行中 demo 执行验收与双 worker 抢占校验：
  ```bash
  uv run python scripts/verify_acceptance.py --base-url http://127.0.0.1:8765
  uv run python scripts/verify_acceptance.py --workers
  ```
- 重现 52 张页面截图矩阵与端到端 UI 冒烟检查（需独立临时 demo 目录）：
  ```bash
  cd web && npm ci && npm run screenshots -- http://127.0.0.1:8765
  # 13 页 × 中英文 × 浅深色 → 仓库根目录 artifacts/screenshots/
  ```
  ```bash
  DATAKEEL_HOME="$(mktemp -d)" uv run datakeel demo --port 8773
  # 第二个终端从仓库根目录执行：
  npm --prefix web run smoke:ui -- http://127.0.0.1:8773
  # 截图和报告 → 仓库根目录 artifacts/ui-smoke/
  ```

离线测试边界：S3 通过客户端契约测试验证而不自动连接外部对象存储；外部 LLM 链路仅使用本机 HTTP fixture 校验；中断任务的中间产物保留在磁盘供排查（自动垃圾回收暂未启用）。
