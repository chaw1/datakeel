# Contributing / 贡献指南

Datakeel connects data ingestion, processing, quality, lineage, evidence and controlled actions. Bug fixes, reproducible reports, documentation and focused improvements are welcome. Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

Datakeel 将数据导入、处理、质量、血缘、证据与受控动作连接起来。欢迎提交缺陷修复、可复现的问题、文档和范围明确的改进。参与时请遵守[行为准则](CODE_OF_CONDUCT.md)。

## Set up locally / 本地开发

Use Python 3.12+, `uv`, Node.js 22 and npm. From a checkout of the repository, run:

准备 Python 3.12+、`uv`、Node.js 22 和 npm，在仓库根目录执行：

```sh
uv sync --locked
(cd web && npm ci)
uv run pre-commit install
uv run datakeel demo
```

The demo uses generated local samples and the fake model provider. The [English README](README.md) and [中文 README](README.zh.md) describe the UI, command-line tools and local configuration. Use a separate data directory for experiments and an available port when another demo is already running.

演示使用本地生成的样例和假模型服务。界面、命令行及本地配置见 README。实验使用独立数据目录；已有演示运行时另选可用端口。

## Make a focused change / 完成一个主题

1. Read [AGENTS.md](AGENTS.md), [the architecture](docs/ARCHITECTURE.md) and [code standards](docs/CODE_STANDARDS.md), then inspect the implementation and existing tests. 先读规约、架构、代码规范和真实实现。
2. Keep one change focused on one problem. Add a regression test for a bug and meaningful tests for changed behavior. Use generated data, local fixtures and fake providers. 一次改动解决一个问题，用回归测试说明改动前后行为。
3. Update public documentation and `CHANGELOG.md` when behavior changes. HTTP and tool boundaries use pydantic v2 models; frontend response types come from OpenAPI. 公共行为变更同步文档；接口响应类型不得手写。
4. Run the required gates below. Include the commands, results and any unverified cases in your pull request. 交付时提供验证命令、结果和仍未验证的场景。

For API schema changes and any frontend source change, regenerate the corresponding artifacts before the final gate:

接口 schema 或前端源码变化后，先更新对应产物，再跑最终门禁：

```sh
(cd web && npm run generate:api)
(cd web && npm run build)
make check
```

`make check` enforces public-content scanning, formatting, lint, strict types, layering, size limits, runtime license auditing, test coverage, frontend tests and a production build. Overall Python coverage must remain at least 85%; the modules listed in `docs/CODE_STANDARDS.md` must remain at least 90%. Do not weaken checks to make a change pass. `make fix` applies formatters and safe lint fixes; review its diff.

`make check` 包含公开内容扫描、格式、lint、严格类型、分层、规模、运行时许可审计、测试覆盖率及前端测试和构建。Python 总覆盖率至少 85%，规范列出的模块至少 90%。不得通过降低门禁来交付。`make fix` 可执行格式化与自动修复，执行后检查差异。

For the same extended checks used in CI, run:

复现 CI 的扩展门禁：

```sh
bash scripts/ci-check.sh
```

This also exercises README commands and mutation tests. SQLite is the default. To repeat the gate on PostgreSQL, set `DATAKEEL_TEST_DATABASE_URL` to a fresh local database you own; tests create and remove only their isolated schemas. Never use a shared or production database for tests.

该入口还执行 README 命令和变异测试。默认使用 SQLite；PostgreSQL 验证时将 `DATAKEEL_TEST_DATABASE_URL` 指向自己新建的本地测试库，测试仅创建和清理各自隔离的 schema。不要使用共享库或生产库跑测试。

## Reports and pull requests / 问题与合并请求

Search existing issues before filing a report. Use the bug template for expected and actual behavior, a minimal reproduction, version details and redacted logs. Use the feature template for the user problem, proposed outcome and acceptance criteria. Reports may be written in English or Chinese.

提交前先检索已有问题。缺陷模板需填写预期、实际结果、最小复现、版本和脱敏日志；功能模板说明用户问题、预期结果和验收条件。中文或英文均可。

Keep each commit about one topic and use Conventional Commits, such as `fix(actions): 统一拒绝执行状态` or `docs: clarify local setup`. Review `git diff --cached` before committing. A pull request should explain the problem, resulting behavior, validation and remaining limitations; complete its checklist and link the related issue if there is one.

每个提交只包含一个主题，使用 Conventional Commits。提交前检查 `git diff --cached`。合并请求应说明问题、最终行为、验证结果与限制，完成检查清单，有相关 issue 时附上链接。

## Licensing, privacy and security / 许可、隐私与安全

Contributions are provided under the repository's [Apache-2.0 license](LICENSE). Include only material you have the right to contribute. New dependencies must comply with the license policy in the code standards, including transitive runtime packages and assets bundled into the frontend; retain their notices.

贡献内容按仓库 Apache-2.0 许可提供，请确保有权提交。新依赖及其运行时传递依赖、前端打包资源均须符合代码规范的许可要求，并保留上游声明。

Do not include credentials, personal local paths, private network addresses, customer identifiers or real tenant data in code, logs, screenshots or fixtures. Send suspected vulnerabilities through the private process in [SECURITY.md](SECURITY.md), not a public issue.

代码、日志、截图和样例不得包含凭证、本机个人路径、内网地址、客户标识或真实租户数据。疑似漏洞按 [SECURITY.md](SECURITY.md) 私下报告，不放进公开 issue。

The public-content gate reads current tracked files and untracked files that Git does not ignore, including unstaged edits. Findings report a relative file, line and rule without copying sensitive values. Use reserved domains such as `example.org` for generated email samples; the contributor identity rule still requires GitHub noreply addresses. Run `make check-public` for this scan alone.

公开内容门禁读取当前已跟踪文件及未忽略的新文件，包含未暂存修改；命中仅报告相对文件、行号和规则。生成的邮箱样例使用 `example.org` 等保留域名；提交身份仍要求 GitHub noreply 地址。可用 `make check-public` 单独执行扫描。

Maintainers can prepare a local public copy using the [export guide](docs/PUBLIC_EXPORT.md).
维护者可按[导出指南](docs/PUBLIC_EXPORT.md)准备本地公开副本，发布仍是单独的人工步骤。
