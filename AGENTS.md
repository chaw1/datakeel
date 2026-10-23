# Repository working agreement / 仓库协作规约

These rules apply to human contributors and coding agents alike. Read the actual implementation and the linked documents before making changes.

本规约适用于人类贡献者和编码代理。修改前先读真实实现及相关文档，再判断问题与改动范围。

1. **Quality gates / 质量门禁** — A change is complete only when `make check` passes. Do not lower thresholds or bypass checks. [Code standards](docs/CODE_STANDARDS.md) define formatting, lint, strict typing, import boundaries, size limits, coverage and frontend checks. 改动完成以 `make check` 全绿为准，不放宽阈值，不跳过门禁。
2. **Architecture / 架构** — Follow [the architecture decisions](docs/ARCHITECTURE.md). Dependencies point downward through the declared layers; same-layer exceptions must remain explicit in `.importlinter`. 保持既定模块化单体、语言、存储与前端方案，分层依赖只向下。
3. **Typed boundaries / 类型边界** — Use pydantic v2 models for HTTP, operator and action parameters, MCP schemas and configuration. Do not pass bare dictionaries across modules. Keep boundary models frozen with `extra="forbid"` unless a documented reason requires mutability. 所有模块边界使用模型，数据库行对象不得跨出存储层。
4. **Data and access / 数据与访问** — Use generated fixtures and only explicitly authorized environments. Never commit credentials, private network addresses, customer identities or tenant data. Tests use local fixtures, fake model providers and isolated databases. 先确认资源归属；不得借用已有连接或凭证访问未授权环境。
5. **Dependencies and licensing / 依赖与许可** — Keep runtime additions within the agreed task scope and the permissive-license policy. Preserve upstream notices. The existing exception for unchanged `certifi` root-certificate data is documented in [code standards](docs/CODE_STANDARDS.md); it does not authorize other MPL code. 新依赖要核对传递闭包及前端打包内容，不扩大已有许可例外。
6. **Focused changes / 改动范围** — Preserve unrelated work. Add meaningful regression tests for behavior changes; keep user-visible documentation and `CHANGELOG.md` current. For frontend changes, regenerate OpenAPI types when needed and rebuild the tracked `datakeel/web_dist` assets before running the gate. 只改任务相关文件，精确暂存，检查暂存差异中没有凭证或无关改动。
7. **Commits and publication / 提交与发布** — Use one focused local commit per topic with a one-line Conventional Commit title, for example `fix(actions): 统一拒绝执行状态`. Do not add tool-generated signatures. Do not add remotes, push, deploy or publish without explicit authorization. 本仓协作任务默认只做本地提交，不自行发布。
8. **Reviewable handoff / 可复核交付** — Record completed work, validation commands and results, remaining risks, and the next step in the task's agreed handoff location. Choose reasonable defaults for unspecified reversible details and record the assumption; do not invent requirements. 以明确证据交付，未验证的内容如实标注。

Development setup and contribution steps are in [CONTRIBUTING.md](CONTRIBUTING.md). Report vulnerabilities privately as described in [SECURITY.md](SECURITY.md), and follow the [Code of Conduct](CODE_OF_CONDUCT.md).
