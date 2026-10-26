# Data standards and conformance / 数据标准与落标检查

Field standards define a column's business meaning, physical shape and permitted values. Code lists give typed reference values bilingual labels. YAML contracts are portable; every import, edit, deprecation, mapping confirmation and restore uses a frozen controlled action and explicit human approval. Rule suggestions never create mappings automatically. These features use no model.

字段标准描述字段的业务含义、类型、长度、精度、值域、单位、必填、敏感级别与负责人。码表为有类型的参考值提供中英文含义。YAML 合同可导入导出；导入、修改、废止、确认映射和恢复历史均经过冻结的受控动作与人工签批。规则建议不会自动落成映射，也不调用模型。

## Start with generated data / 从生成数据开始

```bash
uv run datakeel demo --once
uv run datakeel standards demo
uv run datakeel standards list --status active
uv run datakeel standards code-lists --search status
uv run datakeel standards suggestions
uv run datakeel standards coverage
uv run datakeel standards check
```

Use the same `DATAKEEL_HOME` for the CLI and API. The standard demo creates generated clean and deliberately nonconforming tables, approved example definitions and confirmed mappings. It does not change the existing enterprise metric source tables. In the Web UI, open **Data standards**. Search field definitions or code lists, filter Draft / Active / Deprecated, and open an item to read its full definition. **Edit definition** prepares a plan; it does not save immediately. Use **Create field standard** or **Create code list** for new definitions, including typed code values. Complete contracts can also be imported with the CLI or action API below.

CLI 与 API 应使用相同的 `DATAKEEL_HOME`。标准演示创建本机生成的合规表、故意违规表、经过演示签批的定义和已确认映射，不改变原有企业指标源表。Web 打开「数据标准」，搜索字段标准或码表，按草稿、生效、废止过滤，选择条目查看完整定义。「修改定义」只准备计划，签批后才保存。「新建字段标准」「新建码表」可创建定义并编辑有类型的码值。完整合同也可通过以下 CLI 或动作 API 导入。

## YAML contract and schema / YAML 合同与校验

The complete generated example and JSON Schema are in [`contracts/standards/`](../contracts/standards/). Unknown fields, duplicate codes, duplicate typed code values, unresolved code-list references, inverted ranges, invalid precision and invalid regular expressions are rejected. Code values preserve their JSON scalar type: the integer `1` and string `"1"` are distinct.

完整生成示例与 JSON Schema 位于上述目录。导入拒绝未知字段、重复编码、重复的同类型码值、未解析码表引用、反向范围、不合法精度与正则。码值保留 JSON 标量类型，整数 `1` 与字符串 `"1"` 不相等。

```yaml
code_lists:
  - code: account_state
    name: Account state / 账户状态
    version: 1
    status: active
    entries:
      - {value: A, label_zh: 有效, label_en: Active}
      - {value: I, label_zh: 停用, label_en: Inactive}
standards:
  - code: account_status
    name_zh: 账户状态
    name_en: Account status
    description: Approved lifecycle state of an account.
    data_type: string
    length: 1
    code_list: account_state
    required: true
    sensitivity: internal
    owner: account-steward
    aliases: [acct_status, 账户状态码]
    version: 1
    status: active
```

A field can additionally declare `precision`, `scale`, `minimum`, `maximum`, `pattern` and `unit`. Sensitivity is `public`, `internal`, `confidential` or `restricted`. Status is `draft`, `active` or `deprecated`; only active definitions are suggested. Deprecation changes status and preserves history. Existing confirmed mappings remain visible, but an inactive standard is explicitly unverified and does not count as conforming. To change a code list, import its complete replacement entry list at its current version. Changed definitions advance their object version; each committed controlled action adds an auditable revision.

字段还可声明 `precision`、`scale`、`minimum`、`maximum`、`pattern`、`unit`。敏感级别依次为公开、内部、机密、严格受限。状态为 `draft`、`active`、`deprecated`；仅生效定义参与建议。废止保留历史；既有已确认映射仍可见，但非生效标准明确标为未验证，不计为合规。修改码表时，按当前版本提交完整的新码值列表。定义发生变化时对象版本递增，每个提交动作均新增可审计修订。

```bash
# Validate and freeze an import; no definitions change yet.
uv run datakeel standards import contracts/standards/enterprise.yaml --dry-run
# Copy the displayed plan ID into these explicit approval and execution commands.
uv run datakeel standards approve PLAN_ID
uv run datakeel standards execute PLAN_ID
uv run datakeel standards export --output standards-export.yaml
uv run datakeel standards schema
uv run datakeel standards history
# Prepare a restore; approval and execution still use the commands above.
uv run datakeel standards rollback 1
```

Import merges supplied definitions with existing definitions. Replacing a definition uses its current version as an optimistic concurrency check; prepare again after a concurrent change. Importing the same contract does not silently overwrite a newer definition. Restoring an old snapshot creates a new revision, preserves prior revisions and restores both contract semantics and mappings. Revision `0` denotes the initial empty state. `--approve` on import, confirm or rollback explicitly approves and executes in one CLI invocation; omit it to inspect the plan first.

导入合并所提供的定义。替换定义使用当前版本做并发校验；若期间发生变更，应重新准备计划。同一份旧合同不会静默覆盖新版本。恢复历史快照会新增修订，保留旧历史，并恢复合同语义与映射。修订 `0` 表示初始空状态。CLI 的 import、confirm、rollback 可显式加 `--approve` 完成签批与执行；省略时只准备计划。

## Mapping suggestions / 映射建议

Names are split by underscores, punctuation and camel case, normalized through Chinese business vocabulary and common abbreviations such as `cust`, `amt`, `qty` and `no`. Matching compares the column name with a standard's code, bilingual names and explicit aliases. Name evidence dominates; compatible physical types, observed code-list hit rate, range, pattern and nonempty-value evidence refine the score. A minimum lexical score of `0.45` and final score of `0.58` are required. At most three candidates remain, ordered by score and then code; weak evidence produces no recommendation. A matching type alone is insufficient.

名称按下划线、标点、驼峰拆词，并归一中文业务词和常见缩写。列名与标准编码、中英文名及显式别名比较。名称信号为主，类型兼容、码表命中率、范围、正则和非空值比例补充打分。名称分至少 `0.45`、最终分至少 `0.58` 才给建议；最多保留三个，按分数再按编码排序，证据不足时不建议。仅类型相同不会建议映射。

Open **Mapping suggestions / 映射建议**, search a column and read each candidate's scoring reasons. Click **Review mapping / 审阅映射**, inspect the affected column, standard and frozen parameters, then sign the approval sheet. Returning or rejecting leaves the mapping unchanged. CLI equivalent:

```bash
uv run datakeel standards confirm SOURCE/SCHEMA/TABLE/COLUMN STANDARD_CODE
uv run datakeel standards approve PLAN_ID
uv run datakeel standards execute PLAN_ID
uv run datakeel standards mappings
```

## Checks, coverage and quality / 检查、覆盖率与质量

Only confirmed mappings are checked. Rules cover type, maximum length, numeric precision/scale, typed code-list membership, inclusive numeric bounds, full-string regular expressions, null/empty required values, declared unit and sensitivity conflicts. Type aliases are normalized; integer storage is compatible with a numeric standard. Phone/email observations raise the detected sensitivity to at least confidential, using the existing PII patterns. Values from confidential/restricted standards and recognized phone/email substrings are redacted in examples. Each violation includes its rule, observed count and at most three bounded redacted examples.

仅检查已确认映射。规则覆盖类型、最大长度、精度/小数位、同类型码表成员、含边界的数值范围、整串正则、必填空值或空字符串、已声明单位和敏感级别冲突。类型别名会归一，整数存储兼容数值标准。现有电话/邮箱 PII 规则命中时，检测敏感级别至少为机密。机密/严格受限字段与识别出的电话/邮箱样例被脱敏；每项违规保留规则、观测条数及最多三个有长度上限的脱敏样例。

Profiling reads already registered, authorized read-only SQLite/PostgreSQL sources and bounds each table to 10,000 observed rows. Counts describe that checked population. Missing value or unit evidence is explicitly skipped, never counted as passing. A column can have no observed violation while still being partially checked. A truncated source population stays partially checked even when every observed value passes. Coverage uses all registered columns as the denominator; mapped-column compliance counts only fully checked columns without violations. Violation Top N sums rule counts, so one row failing several rules contributes more than once.

剖析仅读取已经登记并获授权的只读 SQLite/PostgreSQL 数据源，每表最多观测 10,000 行。条数只代表已检查总体。缺少值分布或单位证据时显式跳过相应规则，不当作通过。字段可能无已发现违规但只完成部分检查。源总体被截断时，即使观测样本全通过，也仍标为部分检查。覆盖率分母为全部已登记字段；映射合规率仅把完整检查且无违规的字段计为合规。违规 Top N 汇总规则条数，同一行违反多条规则时会多次计入。

The **Coverage / 覆盖率** tab groups results by database, table and owner. Table and column links open catalog objects; **Facts / 事实** includes the same redacted checks. **Standards report / 落标报告** shows field quality and the deterministic report. Quality scores completeness (`required`), consistency (`type`, `length`, `precision`, `unit`, `sensitivity`) and distribution/value validity (`code_list`, `range`, `pattern`), weighted 30/40/30. Each evaluated rule has equal weight within its dimension; unmeasured dimensions are excluded from the total. This column score is separate from file-manifest quality.

「覆盖率」按库、表、负责人分组。表和字段链接进入目录对象，其「事实」页展示同一份脱敏检查。「落标报告」显示字段质量及确定性报告。完整性、统一性、分布/值域维度权重为 30/40/30；各维度内按已评估规则等权计分，未测维度不参与总分。字段质量与文件清单质量分别计量。

## Read API and controlled actions / 读取 API 与受控动作

All reads use `/api/standards`: `/fields?search=&status=`, `/code-lists?search=&status=`, `/contract`, `/export` (YAML), `/schema`, `/profiles`, `/suggestions`, `/mappings`, `/checks?table_id=`, `/report?table_id=`, `/coverage`, `/quality?table_id=`, `/analysis-report?table_id=` and `/history`. Profiles expose metadata and observed counts, with source sample values removed. Existing dataset and catalog response contracts remain unchanged.

读取路径如上；profiles 仅公开元数据与观测计数，移除原始样例值。既有数据集与目录响应合同保持兼容。

Prepare with `POST /api/actions/{action_type}/prepare` and the parameters below. Sign the displayed digest through `POST /api/approvals/{plan_id}`, then execute through `POST /api/actions/{plan_id}/execute`, exactly as other controlled actions. Every standards change requires approval even though it is reversible. The existing [action reference](ACTIONS.md) describes actor binding, expiry, stale plans, one-time consumption and receipts.

| Action | Parameters / 参数 |
| --- | --- |
| `update_standard` | `{ "definition": FieldStandard }` |
| `update_code_list` | `{ "definition": CodeList }` |
| `import_standards` | `{ "contract": StandardsContract }` |
| `confirm_standard_mapping` | `{ "mapping": { "column_id": "…", "standard_code": "…" } }` |
| `rollback_standards` | `{ "revision": 1 }` |

先准备动作，按显示摘要签批，再执行。即使可逆，标准变更也始终要求人工审批。执行身份、过期、并发变更、一次性签批及回执语义复用动作参考。
