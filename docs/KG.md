# Text knowledge graphs / 文本知识图谱

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
