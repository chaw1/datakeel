# 代码规范（全部落成工具门禁）

> 原则：规范只写能被工具检查的条目。`make check` 一条命令跑完所有门禁，CI 跑同一条命令。任何门禁不绿，改动不算完成。

## 1. 一条命令

`make check` 依次执行，任一失败即失败：

```
uv run python scripts/check_public_worktree.py
uv run ruff format --check .
uv run ruff check .
uv run pyright
uv run lint-imports
uv run pytest --cov=datakeel --cov-report=term-missing --cov-fail-under=85
(cd web && npm run lint && npm run typecheck && npm test -- --run && npm run build)
uv run python scripts/license_audit.py
```

另有 `make fix`（ruff format + ruff check --fix + prettier --write）。pre-commit 钩子只跑秒级子集（ruff format、ruff check、prettier）；pyright 与测试留给 `make check` 和 CI。仓库带 `.github/workflows/ci.yml` 跑 `make check`（SQLite + Postgres 服务容器两套矩阵）。

公开内容扫描首先检查工作树中所有已跟踪文件（含未暂存修改）和未忽略的未跟踪文件，复用公开导出的本机路径、内网地址、密钥、内部名称、邮箱及文件大小规则。忽略的本地生成数据不进入扫描；已跟踪文件即使匹配忽略规则也必须检查。报告仅输出相对文件名、行号和规则，不输出命中值。邮箱样例可使用 RFC 2606/6761 保留的 `example.com`、`example.org`、`example.net` 及其子域，以及以 `.example`、`.invalid`、`.test`、`.localhost` 结尾的域名；提交身份仍只接受既有 GitHub noreply 域名。

## 2. Python

- Python 3.12；ruff `select = ["ALL"]`。全局 ignore 白名单只有：`D203, D213`（docstring 风格二选一）、`COM812, ISC001`（与 formatter 冲突）。`per-file-ignores` 允许 `tests/**` 加 `S101, ARG001, ARG002, PLR2004`，`scripts/**` 加 `T201`；每条 per-file-ignore 在 pyproject 里写一句理由。`ANN401` 不进白名单，边界处的 `Any` 用行内 `# noqa: ANN401  # 理由`。
- `line-length = 100` 真实生效，不 ignore E501。
- pyright `typeCheckingMode = "strict"`，0 error 0 warning。公共函数签名不得出现未标注的 `Any`。
- `datakeel/runtime/` 是图与模型框架的适配边界，仅在该目录的 pyright executionEnvironment 中关闭两条诊断：`reportMissingTypeStubs`（锁定 LangGraph 的图构造入口没有完整 stub）和 `reportUnknownMemberType`（`add_node`、`compile`、`stream` 等泛型成员包含第三方未精确标注的类型）。参数、返回值和模块边界仍须显式类型化，其余 strict 规则继续生效；后置根目录 executionEnvironment 保持其它包全部 strict 诊断，禁止包外新增 suppression。
- 复杂度与规模：`mccabe max-complexity = 10`；`PLR0915 max-statements = 40`；参数 ≤ 6（PLR0913）；单文件 ≤ 400 行（测试文件 ≤ 600）、单函数 ≤ 60 行由 `scripts/check_size.py` 检查并列入 `make check`。超限就拆。
- `agent`、`runtime`、`workflows`、`routing`、`delegation`、`memory`、`kg` 与 `kg_eval` 各自最多 1500 行，`extraction_runtime` 最多 600 行，分别由对应的 `*_PACKAGE_LIMIT` 检查，不能互相借用额度。
- 公共模块、类、函数必须有 Google 风格 docstring（ruff D 规则）；私有（下划线开头）可省。
- 错误处理：自定义异常层级 `datakeel.core.errors`（`DatakeelError` 根，按领域派生）；禁止裸 `except:`、禁止 `except Exception` 吞异常不重抛（BLE001）。HTTP 层统一异常到状态码的映射在一处。
- 日志：`structlog` 或标准 `logging` 的 JSON 格式，禁止 `print`（T201），CLI 的用户输出走 `rich.console`。
- 数据边界：pydantic v2 模型，`model_config = ConfigDict(extra="forbid", frozen=True)` 为默认，可变模型要写理由。数据库行对象不跨出 storage 层，出层先转 pydantic。
- FastAPI：路由按领域拆成 `APIRouter` 模块（`datakeel/api/routes/<domain>.py`），不在工厂函数里用闭包定义路由；依赖注入用 `Depends`。
- 配置：单一 `Settings`（pydantic-settings），环境变量前缀 `DATAKEEL_`，禁止在业务代码里直接读 `os.environ`。
- 并发与事务：写路径的事务边界在 service 层函数内一次开合；worker 领取用行锁；所有写入幂等键显式。
- 时间：UTC `datetime`，禁止裸 `time.time()` 作为业务时间戳。

## 3. 分层（import-linter 强制）

```
cli
└── api / worker / agent / runtime / extraction_runtime / kg_eval / mcp / harness
    └── kg / pipeline / quality / lineage / governance / semantic / operators / storage / ontology / actions / evidence / catalog / metrics / ask / workflows / routing / delegation / memory
        └── core                                 （模型、错误、ID、时间，无任何向上依赖）
```

`.importlinter` 定义 layers 合同；同层之间的依赖必须列明为显式例外并写理由。

`datakeel/runtime/` 和 `datakeel/extraction_runtime/` 是允许直接导入模型框架与 SDK 的两个适配目录；后者只负责抽取传输，不使用会话图。forbidden 合同扫描 `langgraph`、`langgraph_sdk`、`langchain_core`、`langchain_openai`、`langchain_anthropic`、`langsmith`、`openai`、`anthropic` 和 `tiktoken` 的外部导入，使其它模块只能经 Datakeel 的类型化接口使用它们。`kg` 领域包不导入这些框架或 runtime。checkpoint 数据库模型与 bytes 读写函数仍在 `storage/checkpoint_store.py`，不得导入框架。

## 4. 测试

- `tests/` 目录结构镜像 `datakeel/`；每个公共模块至少一个测试文件。
- 覆盖率总体 ≥ 85%（`--cov-fail-under`）；`core`、`lineage`、`actions`、`worker`、`harness`、`agent`、`runtime`、`workflows`、`routing`、`delegation`、`memory`、`kg`、`kg_eval`、`extraction_runtime`、`ontology`、`evidence`、`operators/evidence`、`catalog`、`metrics`、`ask` 与 `cli/evidence_benchmark.py` 各 ≥ 90%，由 `scripts/check_coverage.py` 读 coverage.xml 判定并列入 `make check`。领域在 storage 层的事务实现同时计入相应模块，`checkpoint_*.py` 归入 runtime，`workflow_*.py` 归入 workflows，`memory_*.py` 归入 memory，`conversation_children.py` 归入 delegation，`kg_*.py` 归入 kg，`kg_eval*.py` 同时归入 kg_eval；报告缺失目标模块也判为失败。
- 不用真实网络、真实 LLM、真实对象存储；全部走本机 fixture。真实服务集成测试单独标记 `@pytest.mark.integration`，默认不跑。
- 每个 bug 修复附回归测试；每个 golden 用例过变异测试（故意改坏实现必须变红）。

## 5. 前端（web/）

- TypeScript `strict: true`，禁止 `any`（`@typescript-eslint/no-explicit-any: error`）。
- ESLint flat config：`typescript-eslint` strict-type-checked + `react-hooks` + `jsx-a11y` + `import` 顺序；Prettier 统一格式。
- 组件 ≤ 300 行，一个文件一个导出组件；目录 `src/{app,pages,components,features/<domain>,api,lib}`。
- API 客户端由 OpenAPI 生成类型（`openapi-typescript`），禁止手写响应类型；请求层统一错误处理。
- 文案集中在 `src/i18n/{zh,en}.ts`；ESLint 规则禁止 JSX 文本节点出现中文字符（`no-restricted-syntax` 匹配 `JSXText` 含 CJK）。
- vitest + Testing Library：每个 page 和 feature 至少一个渲染测试（`scripts/check_web_tests.py` 校验 pages/features 目录与测试文件一一对应）。
- 构建产物 `datakeel/web_dist` 由 `npm run build` 生成并提交（为了无 Node 也能 `uvx` 跑 demo）；构建时写入 `web_dist/.source-hash`（`web/src` 与 `package-lock.json` 的内容哈希），CI 校验该哈希等于当前源码哈希，源码改了没重建即失败。不做 byte 级 diff。

## 6. 提交与文档

- Conventional Commits：`feat|fix|docs|refactor|test|chore|perf(scope): 摘要`，摘要 ≤ 72 字。
- 公共行为变化更新 `CHANGELOG.md`（Keep a Changelog）。
- `README.md` / `README.zh.md` 的 Quick start 必须可照抄运行；CI 里有一步实际执行 README 的命令。
- 禁止 `TODO` 不带编号：写成 `TODO(#issue)` 或进 `docs/BACKLOG.md`。

## 7. 许可例外（已批准）
- `scripts/license_audit.py` 按锁文件遍历当前 Python 目标环境的运行时传递依赖（含递归 extras），以及前端 production/optional/peer 依赖闭包与实际构建模块/资源的并集。版本、安装包身份及运行时依赖关系必须与锁定元数据一致。审计在前端构建后执行，读取绑定源码哈希的 `.runtime-dependencies.json`，生成 `THIRD_PARTY_NOTICES.md`，并纳入 `make check`。
- 许可白名单为 Apache-2.0、MIT、MIT-0、CC0-1.0、MIT-CMU、BSD-2-Clause、BSD-3-Clause、ISC、PSF-2.0、Zlib、OFL-1.1、0BSD、Python-2.0、Unlicense。新增的 MIT-0、CC0-1.0、MIT-CMU 适用于所有依赖，不按包单独开例外。GPL、AGPL、LGPL、SSPL、未知或缺失许可一律失败；无证据的模糊许可名称与其余白名单外条款同样失败，复合表达式逐项检查，不以 MIT 等子串代替完整许可。
- `certifi`（MPL-2.0，仅根证书数据，httpx/fastmcp 传递引入）：允许。MPL 是文件级弱 copyleft，不改其源码即无义务；其它 MPL 代码包仍需逐个申请。
- `orjson` 仅接受精确表达式 `MPL-2.0 AND (Apache-2.0 OR MIT)`：它是 langsmith 和 langgraph-sdk 的传递硬依赖，分发保持上游源码不变，并保留上游许可文件。
- `regex` 仅接受精确表达式 `Apache-2.0 AND CNRI-Python`：CNRI-Python 为宽松许可。上述两条仅适用于对应 Python 包，不扩展到其它包、前端或额外条款。
- `jsonpointer`、`distro`、`requests-toolbelt`、`tiktoken` 的模糊声明按锁定版本、声明原文（长文本使用 SHA-256）及许可文件 SHA-256 三者共同确认；任一变化必须重新核验。GPL、AGPL、LGPL、SSPL 和未知许可仍然失败。

## 8. 约定（人审，不进门禁）
- 测试命名 `test_<行为>_<条件>_<预期>`；一个测试尽量只断言一件事。
- 关键交互（审批卡确认/拒绝、血缘节点点击、SSE 断线恢复）要有行为测试，验收时抽查。
- 可变 pydantic 模型要在类 docstring 里写明理由。
