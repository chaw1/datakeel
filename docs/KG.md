# Text and image knowledge graphs / 文本与图片知识图谱

Datakeel extracts entities and directed relation candidates from UTF-8 text. Every retained claim keeps its source document, evidence checks, extractor and model. The default demo and evaluation replay bundled recordings locally; they do not call a model or read credentials.

Datakeel 从 UTF-8 文本抽取实体与有方向的候选关系，保留原文、核对结果、抽取器和模型。默认 demo 与评测在本机重放内置录制，不调用模型，也不读取密钥。抽取结果需要人工判断；原文核对通过不代表关系语义一定正确。

## Start offline / 离线开始

```bash
uv run datakeel demo --once
uv run datakeel eval-kg --json
uv run datakeel eval-kg --profile replay-flash --json
```

Use the same `DATAKEEL_HOME` as the API to see saved runs and evaluations. Open **Knowledge graph / 知识图谱** and select **Business notes · knowledge graph demo**. It contains 24 recorded passages, three explicitly labelled scripted long documents and one deliberately truncated example. The recorded run is therefore `partial`; successful passages remain visible. The scripted run uses `fake-long`, not a real model.

与 API 使用相同的 `DATAKEEL_HOME`，即可查看已保存的抽取和评测。在「知识图谱」选择上述数据集：24 篇短文对应真实录制，3 篇长文明确标注为脚本样例，另有 1 个故意截断的样例。因此录制任务显示「部分完成」，成功文档仍可查；长文由 `fake-long` 脚本处理，不冒充模型输出。

Relations show review status separately from source verification. Filter by name, type or either status; inspect a relation to see its source and missing checks. Select rows to accept or reject them through `decide_assertions`. The graph shows distinct accepted, candidate, review-needed and rejected edges. Accepted `kg.same_as` pairs share a display node; rejected pairs do not merge.

关系表分别显示「候选/已接受/已拒绝」与「已核对/待复核」。可按实体名、类型、状态筛选，打开关系查看原文及未核上的位置；批量接受或拒绝仍走 `decide_assertions`。图中使用不同样式，接受的 `kg.same_as` 对才合并显示，拒绝后拆回原节点。图投影不会补出推理关系或传递闭包。

## Schema YAML / Schema 参考

The complete [business schema](../contracts/kg/schema.yaml) declares six entity types, seven relations, extraction rules and two examples. Add another schema YAML under `contracts/kg/` in a source checkout; its `id` is used by extraction plans and `--schema`. Installed wheels carry the same bundled contracts under the package's `_contracts/kg/` directory.

完整业务 schema 包含六种实体、七种关系、规则和两个示例。源码部署可在 `contracts/kg/` 增加 YAML；计划及 `--schema` 按其中的 `id` 查找。wheel 自带同一份合同，位于包内 `_contracts/kg/`。以下是可独立校验的最小示例：

```yaml
id: system-owners
version: '1.0'
entity_types:
  - name: person
    description: A named person.
    aliases:
      Mira Chen: [M. Chen]
  - name: system
    description: A named software system.
relations:
  - name: owns
    description: A person is explicitly responsible for a system.
    domain: [person]
    range: [system]
rules:
  - Extract only explicitly stated relations and quote exact source evidence.
examples:
  - text: Mira Chen owns AtlasBoard.
    entities:
      - {name: Mira Chen, type: person}
      - {name: AtlasBoard, type: system}
    relations:
      - head: Mira Chen
        relation: owns
        tail: AtlasBoard
        evidence: Mira Chen owns AtlasBoard.
```

Names must be unique, domain/range types must exist, and example evidence must be a nonempty substring of its example. Unknown fields are rejected with file/field locations. Aliases are explicit canonical-name-to-spellings mappings within one type; they are not learned from model output. A run never edits the schema. Unknown relation labels, invalid direction/type pairs and ambiguous endpoint types become read-only schema proposals with counts and samples.

类型和关系名不得重复，domain/range 必须引用已声明类型，示例证据必须是示例原文的非空子串。未知字段按文件和字段位置报错。别名显式声明在对应类型内，不从模型输出自动学习。运行不会修改 schema；未知关系、类型或方向不符、端点类型歧义等排除结果进入只读提案，显示计数和样例。

## Extraction profiles / 抽取配置

Profiles under [`contracts/kg/profiles/`](../contracts/kg/profiles/) are selected by `id` in actions. `eval-kg --profile path.yaml` also accepts a separate YAML file; relative `recording` paths then resolve against that file's directory. Bundled profile recording paths resolve against `contracts/kg/`.

动作按上述目录内配置的 `id` 选择。评测还支持外部 YAML 路径；此时录制相对路径以配置文件所在目录为基准，内置配置则以 `contracts/kg/` 为基准。

| Field / 字段 | Meaning / 含义 |
| --- | --- |
| `id`, `extractor`, `provider`, `model` | Required identity. Extractor is `replay`, `fake`, `llm` or optional `gliner2`; offline provider matches the extractor. / 必填身份；离线 provider 与 extractor 相同。 |
| `base_url`, `api_key_env` | Optional endpoint and environment-variable **name**. No key value, URL credential, query or fragment. / 可选地址与密钥环境变量**名称**，不写实际密钥。 |
| `output_method` | `json_schema`, `function_calling` or `json_mode`; default `json_schema`. / 结构化输出方式。 |
| `request_parameters` | Only validated `enable_thinking`, `thinking`, `reasoning_effort`; no arbitrary headers or body override. / 仅允许这些经过类型校验的参数。 |
| `temperature`, `max_output_tokens` | Defaults `0`, `4096`; output limit is per block. / 默认值，输出上限按块计。 |
| `chunk_size`, `chunk_overlap` | Unicode code-point counts; overlap must be smaller than size. / Unicode 码点数，重叠小于块长。 |
| `recording` | Required for replay; optional for a clearly labelled fake script. / replay 必填，fake 可引用明确标注的脚本录制。 |

### Local Ollama / 本机 Ollama

The [bundled example](../contracts/kg/profiles/ollama.yaml) uses the chat-completions compatible endpoint. Use a model already installed in your authorized local environment; Datakeel does not start or download it.

[内置示例](../contracts/kg/profiles/ollama.yaml) 使用兼容 chat-completions 的接口。先自行在已授权的本机环境准备模型；Datakeel 不启动服务或下载模型。

```yaml
id: local-ollama
extractor: llm
provider: openai
model: qwen3.5:9b
base_url: http://localhost:11434/v1
api_key_env: null
output_method: json_schema
request_parameters:
  reasoning_effort: none
temperature: 0
max_output_tokens: 4096
chunk_size: 1000
chunk_overlap: 100
```

The bundled Ollama profile uses 1000-code-point chunks and 100-code-point overlap to preserve context across sentences. Ollama chooses its default context from available VRAM, so it may be only 4096 tokens. The built-in prompt plus one chunk uses roughly 1–2k input tokens, leaving ample headroom; this is an estimate, not a bound for every text or custom schema. Overlong output with `finish_reason=length` is recorded as a failed block. For larger chunks, configure `OLLAMA_CONTEXT_LENGTH` on the Ollama server and restart that server yourself. Its OpenAI-compatible endpoint cannot set context length through a request-level `num_ctx`; Datakeel therefore rejects that parameter. Custom schemas can make prompts larger and need their own context allowance. Provider `prompt_tokens` alone cannot reliably prove input truncation without a matching tokenizer.

内置 Ollama 配置使用 1000 码点块、100 码点重叠，保留跨句上下文。Ollama 按显存设置默认上下文，可能只有 4096 token；内置提示词加一块的输入约为 1–2k token，留足余量。这是估算，并非所有文本或自定义 schema 的上界。输出超长返回 `finish_reason=length` 时记为失败块。更大的块需要在 Ollama **服务端**设置 `OLLAMA_CONTEXT_LENGTH` 并自行重启服务；OpenAI 兼容接口不支持通过请求中的 `num_ctx` 调整上下文，配置中已禁止该字段。自定义 schema 会增加提示词长度，需另行核算。没有同模型 tokenizer 时，不能仅凭 `prompt_tokens` 可靠判断输入截断。

### Compatible cloud endpoint / 兼容云端接口

The [cloud example](../contracts/kg/profiles/cloud.yaml) uses `json_mode` with provider-specific thinking disabled. Replace the model and endpoint only with ones you are authorized to use. Keep the secret in the named environment variable, outside YAML and the repository.

[云端示例](../contracts/kg/profiles/cloud.yaml) 采用 `json_mode` 并关闭对应服务的 thinking。只填写已授权使用的模型及地址；实际密钥放在指定环境变量，不能写进 YAML 或仓库。

```yaml
id: cloud
extractor: llm
provider: openai
model: deepseek-flash
base_url: https://api.deepseek.com
api_key_env: DATAKEEL_KG_API_KEY
output_method: json_mode
request_parameters:
  thinking: {type: disabled}
temperature: 0
max_output_tokens: 4096
chunk_size: 4000
chunk_overlap: 200
```

The cloud profile uses `deepseek-flash`. The historical `deepseek-v4-flash` name in `replay-flash` and its recording remains unchanged; that retired alias currently routes to the newer Flash model. The price snapshot records the supplied 2026-10-24 peak tariff: USD 0.006 cached input, 0.30 uncached input and 1.20 output per million tokens. Off-peak prices are half; peak hours are weekdays UTC 01:00–04:00 and 06:00–10:00. The conservative peak snapshot supports a visible approval cost bound and actual usage settlement.

云端配置改用 `deepseek-flash`；录制与 `replay-flash` 中的历史名称 `deepseek-v4-flash` 保留，旧模型已退役，该别名目前转向新版 Flash。价格按 2026-10-24 提供的高峰价记入快照：每百万 token 缓存输入 0.006、未缓存输入 0.30、输出 1.20 美元；非高峰半价，高峰为工作日 UTC 01:00–04:00、06:00–10:00。签批显示保守费用上限，返回完整用量后以 `actual` 结算。

No fallback silently changes `output_method`. A rejected request becomes a failed block; each actual request has an extraction trace. Automatic retries and SDK tracing are disabled. Rerunning reuses successful cache entries and retries failed blocks. A `length` or `max_tokens` finish reason is a truncation failure, even when its partial JSON parses.

不兼容的输出方式不会被静默替换；拒绝请求会记为失败块，每次实际调用单独计量。自动重试与 SDK 追踪关闭；重新运行复用成功缓存，并重试失败块。即使返回的局部 JSON 能解析，`length` 或 `max_tokens` 结束原因仍按截断失败处理，不写成功缓存。

Prompt `text-kg-v3` includes every schema example's full source and complete entities/relations JSON after the rules and before the source text. Schemas without examples retain a concrete fallback. Approval estimates and model requests use this same prompt, with permitted vocabulary listed as text and no embedded raw JSON Schema. Provider constraints still receive the schema for `json_schema` and `function_calling`. Extra top-level response keys are ignored and counted in `ignored_top_level_keys`; both `entities` and `relations` remain mandatory and strictly validated. Schema-only echoes fail parsing. Failed parsing and truncated responses retain any reported usage in the extraction trace.

提示词 `text-kg-v3` 在规则之后、待抽取原文之前放入 schema 的全部示例，每个示例保留全文及完整实体/关系 JSON；无示例时沿用具体兜底示例。签批估算与模型请求共用这份提示词，词汇范围用文字列出，不贴原始 JSON Schema；约束输出仍向 provider 传 schema。响应顶层多余键忽略并计入 `ignored_top_level_keys`，`entities` 和 `relations` 仍必填并严格校验。只有 schema 的回显仍为解析失败；解析失败或截断的已消费用量仍写入抽取 trace。

## Source checks and identity / 原文核对与身份

Decode UTF-8, normalize text to NFC and keep `[start, end)` Unicode code-point offsets. Split by paragraphs, then sentences, then bounded windows for oversized sentences; overlap never changes the original coordinate system. Evidence matching prefers exact quotation text, then falls back to NFKC normalization, case folding and whitespace-insensitive matching while mapping locations back to the NFC source. Head and tail checks search the supplied full names and explicit schema aliases using these source matchers; the benchmark scorer's shorter-substring alignment is not used for verification.

UTF-8 解码后统一为 NFC，位置用 Unicode 码点半开区间 `[start, end)`。优先按段落、再按句子切块，超长句再切有界窗口，重叠块仍保留全篇坐标。证据优先精确匹配，未命中再尝试 NFKC、大小写和忽略空白的归一化匹配，并把位置映射回 NFC 原文。头尾核对查找所提供的完整名称及 schema 显式别名；评分脚本用于名称对齐的较短子串规则不参与产品核对。

`verified` requires located evidence and both endpoints. Missing checks retain `needs_review` candidates and identify evidence/head/tail failures. A uniquely inferred undeclared endpoint also remains pending review. In the recorded Vivo example, the evidence exists but the tail entity cannot be located. Accepting or rejecting a claim changes its review status, never its source-verification result.

`verified` 要求证据句和头尾实体都定位成功。任一未核上仍保留 `needs_review` 候选，明确指出缺证据、头实体或尾实体；即使 schema 能唯一推定未声明端点的类型，也保持待复核。录制中的 Vivo 例子有证据句，但尾实体不在原文。人工接受或拒绝只改复核状态，不会把失败的原文核对改成成功。

Entity asset IDs are deterministic from dataset/type/normalized name and remain stable across dataset versions; `AssetRef.version` selects the version separately. Each distinct source occurrence keeps its own mention assertion, while duplicate copies from overlapping blocks are deduplicated. Equal oriented triples merge evidence anchors across chunks and documents. Review decisions stay append-only. Within one dataset version, the latest human acceptance or rejection follows the same triple or entity mention across new anchors, selected files and profiles. Inherited decisions record their source assertion and decision IDs; new evidence remains visible. Triples no longer extracted from any document are invalidated. Superseded assertions retain their history; partial documents preserve prior successful facts. Cache keys include content, schema, model, profile, prompt/extractor versions, chunk settings and recording identity.

实体 asset_id 由数据集、类型与归一名称确定，跨数据集版本保持稳定；`AssetRef.version` 单独选择版本。每个不同的原文出现位置保留独立提及断言，重叠块产生的重复副本去重；相同有向三元组跨块、跨文档合并证据位置。人工决定追加记录。同一数据集版本内，同一三元组或实体提及在增补证据、改选文件、换配置后继承最新人工接受/拒绝；继承审计注明来源断言和决定 ID，新证据照常可查。全部文档都不再抽到的三元组仍按原规则失效，旧断言历史保留；部分失败文档保留先前成功事实。缓存包含内容、schema、模型、配置、提示词/抽取器版本、切块参数与录制身份；修改模型名不能命中旧缓存。

Entity types are trimmed and matched case-insensitively to the schema spelling. Unknown types become `unknown_entity_type` proposals with entity samples; relations referencing those types carry the same reason. Proposal counts include excluded entities and relations, with each sample list bounded at twenty.

实体类型先去首尾空白、忽略大小写匹配 schema 正式拼写；仍未知的类型进入 `unknown_entity_type` 提案，包含实体样例，引用它们的关系也使用该原因。计数包含被排除的实体和关系，两种样例各最多二十条。

## Evaluation / 评测

```bash
uv run datakeel eval-kg
uv run datakeel eval-kg --profile replay-flash --json
uv run datakeel eval-kg --profile ./local-profile.yaml --cases ./my-cases.yaml \
  --budget-tokens 250000 --max-cost-usd 5 --json
```

The last command explicitly runs the selected profile; an `llm` profile can send text and incur charges immediately. CLI evaluation is an explicit operator invocation, separate from the UI/Agent approval flow. It reserves budget before each call, records `call_type=extraction`, and refuses to save a complete score report after a budget rejection/overrun. Replay's actual tokens and cost are zero; historical recorded usage remains inside the recording metrics. Unpriced or unreported provider billing is `unknown`, not zero.

最后一条命令会立即运行所选配置；若为 `llm`，可能直接外发文本并产生费用。CLI 评测属于操作者显式执行，与 UI/Agent 的签批流程分开。每次调用先预留预算，trace 标记为 `extraction`；预算拒绝或超限不会保存貌似完整的评测。重放实际 token 和费用为 0，历史模型用量单独保留在录制指标中；价格或用量未知显示 `unknown`，不填 0。

Complete provider usage charges the extraction token budget by actual input plus output even when the price is unknown; unknown cost keeps the conservative monetary reservation. Missing usage keeps the worst-case token reservation. Conversation billing is unchanged. Terminal extraction failures retain completed blocks, calls, usage and charges. JSON, CLI and saved evaluation reports list every failed case with `[start, end)` offsets and its reason.

抽取拿到完整用量时，即使价格未知，token 预算也按实际输入加输出扣；未知费用仍按保守金额预留计，未返回用量才继续按最坏 token 预留扣。对话计费语义不变。整体失败保留已经完成的块、调用、token 和费用。JSON、命令行及持久化评测均逐块列明 case id、起止偏移和原因。

Reports show two independent views, each with all/Chinese/English/verified-only slices, strict triples, undirected pairs, typed/untyped entities, trap hits, grounding and failures:

- **Recording** preserves original unfiltered predictions and original span checks. Fresh profiles use their actual raw predictions.
- **Product candidates** runs the same filtering, endpoint resolution, grounding and merge functions as worker publication. It includes pending-review claims; `verified` is a separate subset.

报告分「录制」和「产品候选」两种口径，各有全部、中文、英文及仅核对通过切片，并报告三元组、实体对、带类型/不带类型实体、trap、定位及失败指标。录制保留原始输出与原始 span 口径；新模型则评它的实际原始输出。产品口径运行与 worker 相同的过滤、端点解析、核对和合并函数，包含待复核候选，不能用已核对子集代替全量。

The scorer's benchmark normalization and gold aliases remain independent of product rules. Optional gold triples contribute neither TP nor FP; unmapped endpoints count as FP. The bundled recordings produce strict recording F1 **0.865** (`replay-demo`) and **0.996** (`replay-flash`); product-candidate F1 is **0.891** and **1.000**. These are measurements on the supplied 24 passages, not model-quality claims for other data. Every excluded relation is reported with its reason. Saved reports are available at `GET /api/kg/evaluations`.

评分脚本的归一化和 gold 别名独立于产品规则。optional 三元组既不计 TP 也不计 FP，无法映射的端点计 FP。内置 24 篇录制 strict F1 分别为 **0.865 / 0.996**，产品候选 F1 为 **0.891 / 1.000**；这些只描述当前数据，不代表其他文本上的模型质量。每个被过滤关系都带原因，历史结果可从上述只读 API 获取。

External suites use the same format as [`cases.yaml`](../contracts/kg/eval/cases.yaml): top-level `id`, optional `version`, and nonempty `cases`. Each case has a unique `id`, `lang: zh|en`, `text`, `entities: [{name,type,aliases?}]`, `relations: [{head,relation,tail}]`, and optional `optional`/`traps` arrays of the same triple shape. Gold types and relation endpoints must match the selected schema. External text may be long and is chunked normally; no corpus-specific text rules are applied.

外部题集使用相同格式，gold 实体类型和关系端点须符合所选 schema。`aliases` 只供评分对齐，`optional` 与 `traps` 默认空数组；外部长文本照常切块，不按内置语料的具体句子作特殊处理。

## Optional GLiNER2 / 可选 GLiNER2

This adapter extracts **entities only**, then uses the same mention grounding. It is not installed by Datakeel and is outside the locked runtime dependency closure. Prepare a separate environment and authorized local **span-model** checkpoint first. The upstream [installation reference](https://github.com/fastino-ai/GLiNER2/blob/main/README.md) specifies the `local` extra for inference; `GLiNER2.from_pretrained` accepts span checkpoints, not newer boundary checkpoints.

此适配器只抽实体，再走同一提及核对；Datakeel 不默认安装它，也不把它加入锁定运行时闭包。先在单独环境准备已授权的本地 **span 模型**。上游[安装说明](https://github.com/fastino-ai/GLiNER2/blob/main/README.md)要求本地推理安装 `local` extra；当前适配接口不加载 boundary 模型。

```bash
uv venv .venv-gliner2
uv pip install --python .venv-gliner2/bin/python . 'gliner2[local]'
```

```yaml
id: gliner-local
extractor: gliner2
provider: gliner2
model: ./models/gliner2-span
chunk_size: 1000
chunk_overlap: 100
```

Use the local directory you prepared, not an unreviewed remote model ID. A remote ID may cause the optional library to download weights. `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` can enforce local-only loading. No weights are bundled; default tests use an injected fake module. Missing installation produces an explicit `gliner2_not_installed` block failure.

模型路径应指向自行准备的本地目录；远程 ID 可能触发可选库下载权重，可用上述两个环境变量强制离线加载。不随包分发权重，默认测试只注入假模块。未安装会明确记录 `gliner2_not_installed` 失败块。

## Outbound consent and threat model / 外发签批与威胁模型

`run_kg_extraction` is discovered through `tool_search`; `query_kg` and `explain_relation` are also discovered reads and are available through MCP. Actions accept `dataset_id`, `version_id`, `schema_id`, `profile_id`, optional `file_ids`, `budget_tokens` and `max_cost_usd`. Use the existing prepare/approve/execute endpoints and a running worker. Extraction creates candidates; reviews use the existing reversible `decide_assertions` action.

图谱动作和两种只读函数均经工具发现提供给 Agent，MCP 共用同一注册表。抽取沿用既有准备、签批、执行与 worker 流程，不新增直接绕过审批的执行入口。准备时只冻结文件 ID、content_revision、块起止偏移和内容哈希、录制文件哈希、schema、完整非秘密配置、请求参数和计费快照。计划和工具返回不复制文档全文、块文本或录制内容。

Plans contain source and recording fingerprints, never source text or recording responses. After authorization, the worker rereads, decodes and chunks every selected document and hashes the recording; any mismatch fails the entire execution before model construction. Verified source snapshots are stored internally for relation explanations. Existing run history remains readable; old prepared plans containing full content must be prepared again.

授权后的 worker 重新读取、解码、切块并核对所有指纹；任一文件、块或录制不符，整次执行失败，不创建模型适配器、不替换为新内容继续。核对通过的原文快照只在内部保存，供关系抽屉使用。既有抽取历史仍可读；旧版含全文的待执行计划须重新准备。

Only literal loopback destinations (`localhost`, `localhost.`, IPv4 loopback or `::1`) and offline extractors avoid external-transfer approval. A private-network address or arbitrary hostname is external; classification never resolves DNS. The approval card shows destination host, model, document/block counts, input estimate, per-call output cap and cost bound, with unknown cost explicit. Any changed destination, model, method, request parameters or input needs a new plan. Secrets are read only when the explicitly selected real adapter executes, not when planning or listing profiles.

仅字面 loopback 地址与离线抽取器不要求外发签批；私网地址或普通域名仍算外发，判断时不查 DNS。签批卡显示目标主机、模型、文档/块数、输入估算、每次输出上限和费用上界，未知费用明确显示。改目标、模型、输出方式、参数或输入都须重新准备计划。列配置和准备计划不读密钥，只在显式真实执行时读取。

Source documents and model responses are untrusted data. Schema restrictions and source checks constrain what becomes a candidate, but they do not prove a statement is true or eliminate prompt injection. A supplied quote may be misleading even when all spans match. No model output can approve a plan, edit schema, alter credentials or call another tool. Frozen plans, server-side authorization and source-scoped audit remain the execution boundary; human review remains the semantic boundary. The default replay path has no outbound request.

原文和模型返回都是不可信数据。schema 与原文核对限制候选形状，但不能证明事实真假，也不能彻底消除提示注入；全部位置匹配的句子仍可能被误解。模型输出不能签批、改 schema、改密钥或调用其他工具。冻结计划、服务端授权和来源审计保护执行边界，人工复核判断关系语义；默认重放路径没有外发请求。

## Catalog associations and knowledge questions / 对应资产与知识问数

Graph `dataset` entities can associate with catalog tables or views; `metric` entities can associate with semantic metrics. Associations are independent candidate assertions under `link.maps_to`, published by `evidence.kg_link`. No model is used for linking, intent recognition or subject resolution. Only the latest published graph version per dataset participates; different datasets retain separate source attribution. Questions do not merge identities through `kg.same_as`. Canonical entity names and their own source-anchored mention spellings participate in subject matching. Distinct graph identities contribute through eligible associations, with an explicit same-name person/organization and catalog-role exception for responsibility questions.

关联只处理图谱的 dataset 和 metric 类型。表标识符用 `[A-Za-z][A-Za-z0-9_]*(?:[./][A-Za-z][A-Za-z0-9_]*)*` 提取，与表名、`schema.表名`、完整目录 id 忽略大小写精确比较；固定停用词是 `table`、`tables`、`the`、`表`。下划线不会拆开，所以 `erp_raw_shipments` 不等于 `shipments`。文字只来自实体名和该实体提及锚点覆盖的片段，不扫描所在整句。

Metric association compares complete names after NFKC normalization, lowercasing and trimming. Entity names and their mention spans additionally allow removing the suffix `指标` or a `metric` suffix preceded by whitespace, an underscore or a hyphen; names such as `geometric` and `biometric` remain intact. Registered names, IDs, terms and synonyms retain their complete spelling. Metric names, IDs and term names form the exact tier; metric and term synonyms form the synonym tier. Only the strongest matching tier is retained. Substring and prefix matching do not create associations.

最强档只命中一个资产是唯一匹配；候选阶段可以作答，显示「关联待确认」。命中多个资产是歧义匹配；多条候选仍存活时，人接受前不用于作答，并按本题方向统计被排除说法的 `pending_ambiguous_links`。其余候选被人工拒绝、只剩一个时，该候选可用于作答，仍保留 candidate「关联待确认」。拒绝的关联及关系不用于回答，也不计入待确认数量。另一端没有可用关联且不剩歧义候选时，说法仍保留；从未匹配目录的标为 `not_in_catalog`，人工拒绝关联的标为 `link_rejected`（关联已被人工拒绝）。已确认的关系不会随另一端关联被拒而消失。人员、组织、地点和系统的另一端标为 `not_applicable`，不会把人误标成「目录里没有」。

Associations rerun after graph publication, catalog import/refresh and semantic installation/update. `POST /api/kg/links/rerun` is the idempotent manual entry point; `GET /api/kg/links` supports dataset and status filters, and `GET /api/kg/entities/{entity_id}/links` serves the entity panel. Review uses the existing `decide_assertions` flow. Metric targets bind the metric version, while table/view targets bind the catalog revision so metadata changes remain auditable. Link decisions inherit by entity ID, predicate and target ID, excluding versions. Graph relationship decisions retain their earlier rule: inheritance only within the same dataset version. A direct restore supersedes older decisions in either flow.

知识问句先在目录和图谱的已知名字里做最长、互不重叠的匹配，再判断被问类型和方向。名称包括指标名、同义词、id、术语，表或视图的短名、schema 限定名及完整 id，角色、图谱规范名与实体自己的提及别名。匹配采用 NFKC、大小写折叠，忽略中英文交界空格；表名末尾的「表」或独立 `table` 可以省略。完整 Latin 标识符不在单词、下划线或限定路径内部匹配；单字符和通用类型名不会被当成主语。长实体名覆盖内部短指标名，不通过模糊扫描猜主语。

相同片段命中多个身份时，未拒绝的关联允许图谱实体归并到对应目录资产；人或组织与角色同名时，以角色作为主语，同时保留同名实体的文档说法。拒绝关联会保留目录资产与文档实体两个独立候选，展示名字、来源数据集和类型。数值路线只匹配目录指标，不受图谱同名实体或拒绝关联影响。未知主语返回 `unknown_subject` 和最多三个建议；相似度只用于建议。

疑问词不必紧邻类型名词：先遮住已识别的主语及其类型修饰，再从剩余问句识别表、视图、汇总、报表、看板、指标、数据、人或团队。焦点取被问名词短语的中心词，例如「表的负责人」问人，`metric source tables` 问表；不会把后续从句中的类型词当成主句的被问对象。中文列举请求和英文 `which ones` 等主问占位词也保留前文的类型焦点。`view`、`summary`、`report` 和 `dashboard` 属于视图层；`what data` 属于数据来源焦点。类型名词出现在主语名称内时，不作为被问对象。

Focus and direction share a bounded main-question scope. Recognized supplementary relative clauses, leading concessive clauses and trailing temporal clauses are masked without shifting token coordinates. A narrow trailing apposition such as `, the downstream metric` describes the subject without reversing the main question. A supported main-clause pronoun can retain the resolved subject, including a subject introduced as the sentence topic. These grammatical rules use shared vocabulary and preserve the matched subject's identity.

Direct restrictive clauses retain the predicate connecting the resolved subject to the requested noun. When the subject occurs inside the relative clause, that clause supplies the relation; when it occurs in the main clause, the noun's relative modifier does not supply the main predicate. This bounded treatment also preserves supported topic references and Chinese attributes without changing subject or focus coordinates.

Catalog levels increase from table to view/summary to metric. A question without a reliable direction uses the relative levels: a higher subject asking for a lower object is upstream; a lower subject asking for a higher object is downstream. Same-level lists still require clarification. Neutral relations such as related, linked, attached, associated and belong underneath, or 相关、有关、关联、对应、挂着, retain the requested catalog type and use these same defaults. Catalog list commands, including show me and 列个清单、给我看看, are knowledge requests. Explicit source/result roles take precedence over these defaults: a subject used as input points downstream, while a result asking for its inputs points upstream. Usage questions beginning with 谁 or who follow that dependency direction. A person focus does not turn an explicit request for suppliers or inputs into ownership; a main question that actually asks who owns or maintains the subject retains `owner`. Formula and how-calculated questions follow the upstream definition and source route.

方向由关系框架中被问的槽位决定：被使用、被依赖或作为基础的一端是来源方；使用者、依赖者、产物或流入目标是结果方。疑问短语占结果方时问下游，占来源方时问上游；主语在句首还是句尾不决定方向。话题可以用逗号、冒号、破折号或 `For` 引出，后续的它、这张表、这个视图、该指标、it、this view、that table、its output 继承该主语身份。指代里的类型名词不作为被问类型。依赖方计数仍返回列表及个数。

| Rule / 规则 | Condition / 条件 | Result / 结果 |
| --- | --- | --- |
| `M1-numeric` | Explicit value requests, business quantities or rankings, excluding catalog-object list/count requests / 明确数值请求、业务数量或排名，排除目录对象列表及计数 | Metric route / 指标路线 |
| `M2-metric-phrase` | A registered metric phrase with time, dimensions or grouping; an exact metric scalar request with time, grouping, reduction or comparison cues / 已登记指标及时间、维度、分组短语，或带时间、分组、归约、比较线索的明确指标数值问句 | Metric route / 指标路线 |
| `M3-metric-fallback` | No recognized knowledge request / 未识别为知识请求 | Existing metric parser, including refusal or clarification / 原指标解析及拒答、澄清 |
| `K0-unknown-subject` | No registered subject / 没有已登记主语 | `unknown_subject` with suggestions / 给出建议 |
| `K1-ambiguous-subject` | Multiple identities / 多个主语身份 | `ambiguous_subject` with choices / 请选主语 |
| `K2-person-owned` | Person, team or role with responsibility focus / 人、团队、角色的职责 | `owned` |
| `K3-person-focus` | Main ownership request, or person/team focus without a reliable dependency role / 主问所有权或维护职责，或问人和团队但未明确依赖角色 | `owner` |
| `K4-direction` | Explicit hierarchy, flow, usage, impact or calculation/source direction / 明确层级、流向、使用、影响或计算来源方向 | `upstream` / `downstream` |
| `K5-metric-source` | Metric asks for a table, view or source location / 指标问表、视图或来源位置 | `upstream` |
| `K6-table-metrics` | Table or view asks for metrics / 表或视图问指标 | `downstream` |
| `K7-location-source` | Source location without another resolved direction / 没有其它已确定方向的来源位置 | `upstream` |
| `K8-ambiguous-intent` | Same-level or otherwise unclear direction; ambiguous employment / 同层或其它方向不明确，工作关系有歧义 | `ambiguous_intent` with intent choices / 请选意图 |
| `K9-hierarchy-upstream` | Higher catalog subject asks for lower-level objects / 上层目录主语问下层对象，如视图问表 | `upstream` |
| `K10-hierarchy-downstream` | Lower catalog subject asks for higher-level objects / 下层目录主语问上层对象，如表问报表 | `downstream` |
| `K11-subject-role` | Grammar identifies the known subject as an input or result / 句式确定主语是输入还是结果 | Input → `downstream`; result → `upstream` |
| `K15-question-slot` | The interrogative occupies the source or result slot, including a topic's pronoun reference / 疑问短语占来源或结果槽，支持话题指代 | Source → `upstream`; result → `downstream` |
| `K16-counterfactual-slot` | A known source is removed, retired or stops supplying data; the question asks for affected results / 已知来源缺失、下线、断供，询问受影响的结果 | `downstream` |
| `K17-flow-slot` | A flow frame asks for its destination or source / 流向框架询问去向或来源 | Destination → `downstream`; source → `upstream` |

Shared terms live in `datakeel/ask/knowledge_vocabulary.py`; `knowledge_frames.py` combines them with argument templates for source, result, counterfactual and flow questions.

| Category / 类别 | Chinese / 中文 | English / 英文 |
| --- | --- | --- |
| Hierarchy / 层级 | 上游、上一层、底下、下游、下一层 | upstream, underneath, underlying, beneath, downstream |
| Flow / 流向 | 来源、源头、输入、基础、依据、去向、下一站、流向、流入、供给 | source, input, basis, foundation, feeds, fed into, powers, supports, supplies |
| Impact / 影响 | 受牵连、波及、连累、受影响；条件句中的停用、消失、删除 | affects, impacts, breaks, suffers; if/without with removal or unavailability |

Source-role templates include 以/拿/用/把 X 当作来源、输入、基础、依据, `fed by X`, `derived from X`, `built on X` and `pull from X`. Result-role templates include X 的来源/源头 and `X is fed by`. Active and passive dependency or production forms distinguish the input from the result; nominal forms such as `source for X`, `X as input` and `X as output` also retain that distinction. Predicate arguments identify the input and result, with the interrogative phrase selecting the requested side. A generic source noun alone does not override an explicit subject role or an available cross-level catalog default. 角色不明确的弱来源名词不会覆盖跨层级默认方向。

双论元句式分别定位接收对象与输入，例如 `feed/build/supply receiver with/from/using input` 和「用/拿输入生成结果」；已知主语落在输入一端时问下游，落在接收对象或结果一端时问上游。句式中的代词回指也区分「它使用的对象」与「使用它的对象」，不只按依赖词相对主语的位置判断。

被问对象前的层级形容词不会覆盖同一主问句中明确绑定主语的使用、生产、被动或条件角色；直接询问上下游及弱来源介词仍保持原方向。中文主题前置并省略宾语的使用问句，以及使役和接收者句式，也按使用者与被使用对象区分方向。单字使用动词需要对应的句式或明确词边界，不把「读数」「用途」等词中的单字当作方向词。

条件句中的缺失或停用事件只在条件分句内定位，不取结果分句里的同类动词。主题前置和逗号保留主语角色；事件背景只有在主问明确询问影响时才作为来源线索。英语 `used to/for/when` 生产目的句区分直接结果名词与来源介词补语，并保留主动使用者和被动资源的差别。

明确的「流入」和 `fed into` 按主语相对目标补语的位置区分来源与接收方；「给/为主语提供数据」把主语识别为接收方。`subject appears on` 和「看板/报表/视图显示主语」识别展示消费关系；明确询问显示数值时仍保持指标路线。

`AskAnswer.recognition` 保存匹配片段及主语类型、焦点词、方向词和规则编号；界面的「问题中的匹配证据」展示这些记录。知识推断不确定时使用反问，`knowledge.intent_candidates` 给出可选意图；点击按钮通过可选 `knowledge_intent` 重问，并保留原问题和已选主语。


| Intent / 意图 | Examples / 例句 | Document direction / 文档关系 |
| --- | --- | --- |
| Owner / 负责人 | `出货额由谁维护？` · `Who is responsible for customer_count?` | `owns`, subject at tail / 主语为尾 |
| Upstream / 上游 | `shipments 从哪来？` · `What is sales_summary derived from?` | `derived_from` / `computed_from`, subject at head / 主语为头 |
| Downstream / 下游 | `哪些指标依赖 orders？` · `What uses orders?` | `derived_from` / `computed_from`, subject at tail / 主语为尾 |
| Responsibilities / 负责什么 | `周岩负责哪些？` · `What does treasury team own?` | `owns`, subject at head / 主语为头 |

Numeric and ranking cues (including highest/lowest/largest/smallest and 最大/最小) keep the metric route unless the question requests catalog objects. 几个/多少个/多少张 or `how many` followed by a catalog type asks for a knowledge list and its count; `how many orders` and 订单数是多少 remain business measurements. Cues embedded in a registered name are not quantities. 哪几、几张 and 几位 are list expressions. Pure metric phrases remain numerical after removing metric names, time, dimension values, grouping clauses and filler words; grouping by owner or source is still numerical. Typed person/team, table, view, metric-list and source questions never execute a numeric query merely because they ask for object counts. Other wording retains the existing metric parser and its refusals or clarifications.

分组维度中的 owner、source、upstream、downstream、负责人、来源不是知识焦点。`by`、`per`、`for each`、`group by`、`break down by`、`each dimension's metric` 和「按／分／每个维度」保留指标路线；前置分组之后真正询问负责人或来源的主句仍走知识路线。时间修饰可以带所有格；没有知识焦点的时间加指标数值问句走指标路线。无数值线索的主问「谁／哪位／who」仍不能进入指标路线。

明确把 value、amount、quantity、reading 或「数值、读数、金额」作为所求结果的问句走数值路线；`reading` 作读取动作时仍按依赖关系解释。来源、负责人和公式是知识请求，目录类型的数量请求仍保留对象列表与计数，不因句中出现数值名词而改为业务数值。

总额、合计和 `total` 同样按主问对象处理：求总额时，附属分组中的团队、人员或表名不会变成知识焦点；问总额的负责人、来源或公式时，数量修饰词也不会替代知识焦点。纯指标短语先辨别分组和显式筛选从句中的修饰性疑问代词，保留直接询问对象或来源的疑问词。

完整指标别名中的数量词被主语遮蔽后，仍保留明确的值请求：仅当剩余结构精确询问已登记指标，并且原句有时间、分组、统计归约或数值线索时，英文表语问句走指标路线。来源、负责人、公式等关系中心词不会被该规则吞掉；缺少这些值线索的泛问仍可反问。`on top of` 的结构含义不作为数值排名，影响句式则按变化来源与受影响对象区分方向。

分组修饰不能吞掉同句后面的来源、负责人或目录对象主问；「各类数量」「各项金额」等明确输出名词也不会被当作分组字段删除。明确的已登记指标阈值比较及数值输出命令保持指标路线，同时保留目录类型和关系主问。服务回归直接禁止这些知识问句执行 SQL，并检查结果为空及持久化回读。

数目录对象时，数量短语可以位于类型名词前，或明确地置于问题末尾；中英混排的类型词也保留词边界。答案保留请求类型的列表，并分别列出系统登记和文档提及的个数。每部分按对象身份去重，保留各条文档说法的审核状态；两部分不相加成一个总数。表与视图按已关联目录对象的类型区分；未关联的文档 `dataset` 只参与泛指「数据对象」计数，不猜测为表或视图，明确请求表或视图时说明排除的类型未明对象数。待确认的歧义关联另行说明，不计入已列对象。计数只代表本次返回的当前记录，不声称是目录之外的完整总量。

A knowledge answer uses `answer_kind=knowledge`, a separate `knowledge` payload, and `subject_candidates` for ambiguity or suggestions. A resolved subject with no facts returns `no_knowledge`; ambiguous document associations return `pending_links` when no other facts are available. Pending counts remain visible in all states. Successful numeric answers add at most five related document claims with `intent=related`; missing source revisions omit only the unavailable optional claims and preserve the numeric result. Every route records its deterministic recognition rule.


问答卡分「系统记录」和「文档里的说法」。系统侧：指标负责人取语义层角色，表负责人读 `owned_by`；指标上游是度量表，表/视图上下游聚合列级 `derived`，下游另加 `measures` 指向本表列的指标。度量表尚未导入目录时，系统仍显示指标定义里的完整表 id，引用版本标为 `semantic/指标id/指标版本`，不冒充目录修订号；文档另一端仍按真实关联判定。外键、术语、维度不算上下游。角色负责什么取指向该角色的 `owned_by` 指标；人员或团队固定说明系统只登记角色，未登记到人。

Document claims expose the assertion ID, endpoints, predicate, `relation_status` (`candidate` / `accepted`), `verification` (`verified` / `needs_review`), exact evidence fragments and document names. `subject_link` and `other_end` retain the association IDs and independent review states. Upstream/downstream consistency is `consistent` when the other asset is in system records, `not_in_system` when it is linked but absent there, and `not_in_catalog` when unlinked. Owner and responsibility questions have null consistency; same-name people/organizations and roles share a question subject while system and document records remain separate. Clicking a claim opens its source relation drawer. Every used system asset, graph assertion and link assertion is audited with `ask.cites_asset` / `ask.cites_assertion`. Clarifications and refusals additionally record `ask.knowledge_unresolved`, including unknown subjects and ambiguous intents. Cards localize relationship labels; the source drawer retains the raw predicate. Cards show recognition evidence and readable asset names; raw asset identifiers remain in the source drawer.

演示另外导入「企业文档 · Enterprise documents」六篇虚构文档，通过 `replay-enterprise` 离线抽取。原文与录制逐字保存在 `docs/p9/`；写入抽取文档时不附加换行。`eval-ask` 保留原 20 条指标用例的纯目录夹具和统计，另跑 23 条知识/反例用例的初始、审后两种状态；审后严格依次人审、重关联、同版本重抽。报告的 `knowledge.states` 保存逐条答案和检查结果，知识用例要求两态全过。

关联上下文在 SQL 中只读取相关实体的活跃 `kg.%`、`link.maps_to` 断言及 `evidence.kg` 抽取事件；无关问答审计不会随提问次数进入读取结果。回答复用这些事件的冻结文档，以文件 id、版本及内容修订精确选择原文；不会拿其他修订替代缺失证据，也不再为每条说法扫描历史事件。人审夹具的关系及关联决定存放于 `contracts/ask/enterprise-reviews.yaml`，由冻结模型加载，执行代码不包含用例姓名和指标名。


## Images and scans / 图片与扫描件

`run_kg_extraction` accepts images alongside text. Set `transcription_profile_id` (default `replay-image-demo`) independently from `profile_id`, the **text extractor**. Select `replay-image-flash` for the bundled qwen visual transcripts. `mode_overrides` maps selected image file IDs to `ocr` or `vlm`. There is no automatic routing or cloud localization in this release.

`run_kg_extraction` 复用现有签批与任务队列。图片先转写，再走原有文本切块、三处核对和候选断言；`transcription_profile_id` 指转写配置，`profile_id` 仍指文本抽取配置。按文件覆盖通过 `mode_overrides: {文件ID: ocr或vlm}`。本期只提供显式模式，不做自动分流或云端框定位。

```bash
uv run datakeel eval-kg --suite image --json
uv run datakeel eval-kg --suite image --profile replay-image-qwen --transcription-profile replay-image-demo --json
uv run datakeel eval-kg --suite image --profile replay-image-rapidocr-qwen --transcription-profile replay-image-rapidocr --json
```

Image evaluation defaults to offline replay. It stores both original-recording scores and scores read from persisted product assertions in evaluation history. Reports separate clean text, scans, diagrams, Chinese and English, and include strict/entity-pair F1, traps, localization, character error rate, exact identifier preservation and failures. Recording localization compares one enclosing OCR rectangle; product localization compares the geometric union of all image rectangles with gold at IoU ≥ 0.5. A clean/scan pair with identical transcript bytes shares one extraction recording, retaining the lexicographically first case ID. Original failed extraction recordings remain failures with zero predictions.

评测默认离线回放，记录口径与产品口径同时入库。录制口径把一条关系的多个框合成外接矩形；产品口径使用全部框的几何并集，IoU ≥ 0.5 才算命中。清晰/扫描转写逐字相同的用例按 case ID 字典序最小保留抽取录制，原始报错录制按失败和零预测处理。标识符指标逐字比较，不抹掉下划线。评测集为 60 张合成图片，保留原版 b09，不包含真实手写数据、字体文件或生成脚本。

For external cases, pass `--cases ./image-cases` with a `cases.yaml` and images using the same format as [`contracts/kg/eval/image/cases.yaml`](../contracts/kg/eval/image/cases.yaml). Gold boxes are optional; absent boxes are excluded from localization denominators. `--profile` and `--transcription-profile` also accept explicit YAML files for isolated experiments. Real profiles are opt-in and may contact the configured provider; ordinary demo and CI use replay/fake.

外部评测目录放 `cases.yaml` 和图片，实体类型、关系词必须属于所选 schema；标准框可不填。真实评测配置由使用者显式选择。默认 demo、测试和打包验证均使用离线录制，不读取模型密钥。

### Transcription profiles / 转写配置

Profiles live under `contracts/kg/transcription-profiles/`. Every profile is frozen and rejects unknown fields, raw secret values, unsupported backends/modes and non-allowlisted request parameters. `api_key_env` names an environment variable; its value is read only when a visual request actually executes. Request parameters permit `enable_thinking`, `reasoning_effort`, and native Ollama `num_ctx`; they cannot override destination, credentials or output limits.

转写配置位于上述目录，未知字段、密钥值和白名单外参数加载即拒绝。模型、提示词版本、模式、参数、OCR 版本与录制文件哈希都会影响缓存。转写录制只按原图内容哈希查找，成功结果持久化；同样输入重跑时转写和文本抽取都从缓存读取。

```yaml
id: local-vision
backend: vlm
mode: vlm
model: qwen3.5:9b
interface: ollama
base_url: http://127.0.0.1:11434
prompt_version: image-transcription-v1
max_output_tokens: 4096
timeout_seconds: 120
request_parameters:
  num_ctx: 16384
  enable_thinking: false
```

Native Ollama preserves `num_ctx` and maps `done_reason` to the common finish reason. To use a compatible cloud endpoint, use `interface: openai`, an explicit `base_url`, `model: qwen3.5-flash` and `api_key_env: DASHSCOPE_API_KEY`; see the bundled cloud example. The client ignores proxy environment variables, does not follow redirects and never retries `403 AllocationQuota.FreeTierOnly`, reported as “账户只允许免费额度，且已用完”.

Ollama 原生接口支持 `num_ctx`，避免兼容接口默认上下文截断。百炼示例使用 OpenAI 兼容接口与环境变量名；不会把密钥写入配置、计划或录制。免费额度限制返回明确说明，不作为网络故障重试。

RapidOCR is loaded lazily and pinned to 3.10.0; ONNX Runtime is explicitly included in the optional `ocr` extra. Missing OCR reports an installation instruction. Visual mode still runs local OCR to obtain line geometry; replay and fake carry their own frozen OCR lines. The optional dependency audit currently fails: rebuilding OpenCV without FFmpeg resolves its codec finding, but ONNX Runtime still bundles Eigen under MPL-2.0 without an approved exception. See the exact installation and license limits in [code standards](CODE_STANDARDS.md).

RapidOCR 仅进入可选安装，固定 3.10.0 及其随包模型；真实 VLM 转写仍需 OCR 行框。缺少可选库会明确提示安装，回放与脚本无需安装 OCR。当前可选依赖许可未通过：OpenCV 禁视频源码构建可消除其编解码库问题，但 ONNX Runtime 所含 Eigen 的 MPL-2.0 尚无批准例外。具体证据与可复现命令见代码规范。

User-hosted OCR models can use the same OpenAI-compatible boundary. Example profile substitutions: `model: PaddleOCR-VL` or `model: HunyuanOCR`, `interface: openai`, `base_url: http://127.0.0.1:8000/v1`, `backend: vlm`, `mode: vlm`. Run these servers separately; they are not dependencies of Datakeel. These document OCR models are unsuitable for diagrams that require arrow, style and legend transcription. HunyuanOCR's community license does not authorize use in the EU, UK or South Korea; users must check the applicable model license before deployment.

用户自建 PaddleOCR-VL 或 HunyuanOCR 服务可使用相同接口，独立运行，不安装到平台核心环境；它们不适合箭头、虚线、图例等结构图。HunyuanOCR 社区许可不授权欧盟、英国、韩国使用，部署前核对模型许可。

### Provenance, quality and consent / 来源、质量与签批

All coordinates use original pixels **after EXIF orientation correction**. Before any external transfer, the image is re-encoded without EXIF/GPS metadata. Text spans bind the derived `image_transcript` asset, whose ID is deterministic from the image and profile and whose version is the text hash. Image regions bind the original image content revision. Changing the transcriber creates new derived provenance and invalidates replaced assertions with an audit; human decisions survive using the existing review rules.

坐标统一为 EXIF 转正后的原图像素。外发前重编码去掉 EXIF/GPS；转写稿是独立资产，文字位置绑定转写稿，图框绑定原图内容版本。换转写配置生成新的来源与断言，保留旧断言的失效审计和原有人工结论。`rebuild-evidence` 从持久化证据重建，不调用模型，重建前后规范化哈希一致。

Evidence fragments are aligned to OCR text after whitespace/markdown normalization. Exact matches take priority, fuzzy matching uses threshold 0.8, and adjacent OCR lines can match one fragment. Arrows, pipes, ellipses and newlines split fragments; repeated labels choose the occurrence closest to the rarest fragment. A successful text extraction without an image match remains a candidate with `image_unlocated` (“图上未定位”), never an invented rectangle. Dataset metadata `handwriting: true` additionally marks mentions and relations involving entity types declared `person: true` with `handwriting_name` (“手写人名需复核”). Schemas without that marker do not apply this rule.

图片证据框只来自 OCR 行，不采信模型自报坐标。未匹配到框时保留关系并标待复核；转写稿仍可高亮证据句和头尾实体。导入时可通过数据集 metadata 设置 `handwriting: true`；schema 用 `person: true` 指定人物类，这类提及及关联关系始终需要人工核对姓名。

Empty output, truncation, timeout, three consecutive identical lines or repeated long fragments become explicit failed image blocks and a partial report. The 2.5× output/OCR length check applies only when normalized OCR text has at least 20 characters; empty OCR plus valid visual transcription is allowed. Failed results never enter the successful cache.

空输出、截断、重复、超时都进入失败报告；OCR 文字不足 20 字时不使用 2.5 倍规则。失败图片不会静默消失，也不污染成功缓存。报告列出每张图片的路线、缓存、失败原因、已定位/未定位关系以及外发调用和费用。

Preparation reads no transcription backend. Consent binds image hashes, both profiles and both recording hashes. Either non-loopback endpoint requires approval. The card lists image destination/model/count, `ceil(width × height / 1024 + 2)` image tokens, output limit and known/unknown cost; extraction is explicitly estimated from the transcription upper bound, conservatively accounting for UTF-8 bytes and chunk prompt overhead. Visual calls use the same durable reserve/settle budget as extraction, with `call_type: transcription`.

签批前绝不转写。转写端和抽取端分别判断外发，任一非回环端点都要签批；卡片显示主机、模型、图片数、图片 token、单次输出上限、费用上限，查不到价格写未知。抽取输入按转写上限保守估计，并计入提示词及切块开销；两阶段共用预算，转写 trace 单独标记。
