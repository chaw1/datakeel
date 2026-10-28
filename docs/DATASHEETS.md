# Dataset datasheets / 数据集说明书

[English tour](DEMO.en.md) · [中文导览](DEMO.md)

## English

Open a dataset from **Data library**, then select **Datasheet**. Choose a dataset version and document language. **Offline template** produces a deterministic draft without a model or external service. **Generate draft** prepares a controlled action; review it and choose **Execute action**. Generating another draft keeps earlier documents in **Saved drafts and publications**.

Each document contains seven chapters: motivation, composition, collection, preprocessing, uses, distribution and maintenance. Datakeel first freezes available platform facts with a stable fact ID, source object type and ID, field, value and recording time. It then writes sentences from those facts. Missing chapters explicitly say that the platform has no record; this is a disclosure of missing information, not an assessment of the dataset's suitability.

Every retained sentence cites facts. The offline template writes one labelled sentence per fact and one sentence per processing step (operator, state and time), in recorded order. Lists, count tables, scored quality dimensions, issues and graph entities read as plain text (for example `completeness: 100.0` or `person: Maya Chen`); deeply nested or mixed values are shown verbatim. A readable sentence is kept only if it passes the citation check on its own; otherwise the literal value is shown, and the complete value is always one click away. Hover over a sentence for a short source summary, or click it to expand the complete cited facts and timestamps. **Removed sentences** lists rejected text and reasons, including missing citations, unknown fact IDs, unsupported numbers, dates or proper names, wrong chapters and invalid output structure. A chapter with recorded facts but no valid sentence is labeled separately from missing facts. Rejected text is never part of the retained narrative. Citation checks establish support in the stored facts; they do not independently verify the truth of the original data.

**Configured model** uses the selected provider and model under the existing budget and external-transfer approval rules. The offline fake provider can exercise the model path without credentials. Real providers require the user's existing configuration; credentials are never supplied through this form. Review the frozen action before execution. A queued run appears in **Runs**; refresh the datasheet tab after completion. A model supplies candidate wording only: the same independent citation validator checks its sentences before saving.

Each fact sent to the model carries its display label, a value kind (`count`, `ratio`, `percent`, `score`, `bytes`, `amount`, `duration`, `date`, `name`, `status`, `text`, `number` or `record`), a unit for measured values and, for a single value, a display line such as `File count=1,234 files`, `Image share=0.983 (ratio)` or `负责人=张三（名称）`. The prompt asks the model to name fields with those labels, copy numbers exactly as displayed without rounding, converting or totalling, and to write a percentage only for a ratio fact. Saved documents record the kind and unit of every fact.

For an OpenAI-compatible model, the generation body may add `request_parameters` with the same typed controls as transcription profiles: `enable_thinking` (boolean) and `reasoning_effort` (`none`, `minimal`, `low`, `medium` or `high`). Ollama's `num_ctx`, other names, other providers and template mode are rejected. The parameters are frozen in the reviewed plan, sent as request body fields and cannot change the destination, credentials or output limit. For `qwen3.5-flash`, use `{"enable_thinking": false}` to turn off thinking mode. Its entry in `contracts/model-prices.yaml` is the Alibaba Cloud Model Studio list price for the China (Beijing) region and inputs up to 128K tokens, USD 0.029 input and 0.287 output per million tokens (price page updated 2026-10-27). No cache-hit price is published, so cached input is estimated at the full input price. Longer inputs (up to 256K or 1M tokens) and the international (Singapore) deployment cost more and are not modelled; check the provider's current price page before relying on an estimate.

Documents belong to one immutable dataset version. A newer version marks earlier documents **Out of date** without rewriting their facts or text. Select the newer version and generate another draft, or choose **Regenerate for latest version** on an out-of-date document. This shortcut reads the current version list before preparing its plan. Choose a saved document in **Compare with a saved datasheet** to read both documents side by side, with each version's own citations and rejected sentences. **Changes between the two datasheets** lists added, removed and changed facts and the affected chapters; facts recorded on a dataset version are matched by source type and field, so a changed file count appears as one change. History and comparisons are limited to the selected dataset and document language.

**Publish datasheet** prepares a separate action that requires approval. Preparing a publication does not publish it. Approval binds the frozen plan and must precede execution. Publication preserves the document's version and fact snapshot. **Download Markdown** and **Download HTML** export the selected saved document; the HTML also exposes sentence citations and an evidence fact list.

### HTTP entry points

| Method and path | Result |
| --- | --- |
| `GET /api/datasets/{dataset_id}/datasheets` | Saved documents, optionally filtered by `version_id` |
| `POST /api/datasets/{dataset_id}/datasheets` | Generation action plan; body includes `version_id`, `language` (`zh` or `en`) and `mode` (`template` or `model`); model mode adds `provider`, `model` and optional `request_parameters` |
| `GET /api/datasheets/{sheet_id}` | Saved document with facts and citation results |
| `GET /api/datasheets/{sheet_id}/download?format=markdown` | Markdown download; `format=html` returns HTML |
| `POST /api/datasheets/{sheet_id}/publish` | Publication action plan |
| `GET /api/datasheets/{before_id}/compare/{after_id}` | Changed facts and chapters between two saved documents |
| `GET /api/datasheets/jobs/{job_id}` | Durable progress of a queued model generation job |

Use the existing action approval and execution endpoints to finish prepared plans. Generation and publication share the normal action audit and receipt flow.

## 中文

在「数据库」打开数据集，选择「说明书」页签，再选择数据集版本与说明书语言。「离线模板」不需要模型或外部服务，确定性生成草稿。点击「生成草稿」后先查看受控计划，再点击「执行动作」。重新生成会保留旧稿，可在「草稿与发布历史」选择。

每份说明书固定包含动机、构成、采集、预处理、用途、分发、维护七章。系统先抽取并冻结可用的平台事实，每条事实包含稳定 ID、来源对象类型与 ID、字段、值和记录时间，再依据事实撰写句子。缺事实的章节明确标出「平台中没有这一项的记录」，不能据此推断数据集适用性。

保留的每句话都引用事实。离线模板每条事实写一句，每个处理步骤（算子、状态、时间）按记录顺序合成一句。列表、计数表、质量维度得分、问题和图谱实体写成普通文字（如 `completeness：100.0`、`person：Maya Chen`），多层嵌套或混合结构原样展示。可读写法必须单独通过引用校验才保留，否则改用原始取值；完整取值始终可以点开查看。悬停查看来源摘要，点击句子展开完整依据及时间。「已删除的句子」保留被拒绝文本及原因，包括没有引用、事实 ID 不存在、引用事实不支持数字、日期或专有名词、引用其他章节事实，以及输出结构不符。已有事实但没有句子通过引用校验时，会单独说明，不显示为缺事实。拒绝文本不会进入正文。引用校验确认句子能否得到已存事实的支持，不独立证明原始数据真实。

「已配置模型」使用所选服务商与模型，遵循现有预算和外发签批规则。离线 fake 可在没有凭证时演练模型路径。真实服务需要用户已有配置，表单不接收密钥。执行前须核对冻结的计划；排队任务可在「运行记录」查看，完成后刷新说明书页签。模型仅提供候选措辞，落盘前仍须逐句通过独立引用校验。

交给模型的每条事实都带字段标签、取值类型（`count` 计数、`ratio` 比例、`percent` 百分比、`score` 分值、`bytes` 字节、`amount` 金额、`duration` 时长、`date` 日期、`name` 名称、`status` 状态值、`text` 文本、`number` 数字、`record` 结构化记录）、计量值的单位，单值事实另附一行原样写法，例如 `文件数量=1,234 个`、`图片占比=0.983（比例）`、`负责人=张三（名称）`。提示词要求模型用这些标签称呼字段，数字照原样引用，不四舍五入、不换算单位、不求和；只有比例类事实可以写成百分比。已存说明书同时保存每条事实的类型和单位。

使用 OpenAI 兼容模型时，生成请求可附 `request_parameters`，写法与转写 profile 一致：`enable_thinking`（布尔值）和 `reasoning_effort`（`none`、`minimal`、`low`、`medium`、`high`）。Ollama 专用的 `num_ctx`、其他参数名、其他服务商和离线模板都会被拒绝。参数冻结在待审计划中，作为请求体字段发送，不能改变目标地址、凭证或输出上限。`qwen3.5-flash` 建议传 `{"enable_thinking": false}` 关闭思考模式。`contracts/model-prices.yaml` 中它的价格取自阿里云百炼官方价目页（2026-10-27 更新）中国内地（北京）地域、单次输入不超过 128K token 的档位：每百万 token 输入 0.029 美元、输出 0.287 美元。官方未公布缓存命中价，缓存输入按完整输入价估算；更长输入（256K、1M 档）和国际（新加坡）部署价格更高，未纳入估算，依赖估算前请核对服务商当前价目。

说明书绑定一个不可变数据集版本。数据集产生新版本后，旧稿标为「已过期」，旧事实与文本保持原样。选择新版本重新生成，或点击过期文档旁的「为最新版本重新生成」；快捷动作会先读取当前版本列表再准备计划。「与历史说明书对比」可并排查看两稿，每份均展示自己的依据和删句记录；上方「两份说明书的差异」列出新增、删除和变化的事实及所在章节，记录在数据集版本上的事实按来源类型与字段对齐，例如文件数量变化显示为一条变化。历史和对比只展示当前数据集、所选语言的说明书。

「发布说明书」会准备独立的待签批计划；准备计划不会立即发布。签批绑定冻结计划，之后才能执行。发布保持原有版本和事实快照。「下载 Markdown」和「下载 HTML」导出当前选中的已存说明书；HTML 同样支持逐句依据和完整事实表。

HTTP 入口见上表，生成参数中的 `language` 为 `zh` 或 `en`，`mode` 为 `template` 或 `model`；模型模式另需 `provider`、`model`，可选 `request_parameters`。计划通过现有动作审批、执行接口完成，生成与发布均保留通常的审计和血缘回执。

## Citation rules / 引用规则

A sentence must cite at least one existing fact from its own chapter. Every number must equal a value in the cited facts after normalization: thousands separators, full-width digits, decimal or scientific notation, and English or Chinese written numbers are accepted. Numbers are also matched by meaning. A percentage may restate only a ratio fact (`0.983` as `98.3%`) or a recorded percentage, never a count, score, byte total or plain number; `50%` cannot cite a file count of 50. A number written with a unit (files, bytes, points, seconds, a currency or a date part) must match a fact of the same unit or an untyped number; `4,815,739 files` cannot cite a byte total. A bare number may match any cited value. Numbers inside recorded text are typed by the words around them, so `200 generated images` supports `200张图片`. Clock times in a recorded timestamp count as date parts. Dates are compared as calendar days across ISO, slash, Chinese and English month-name forms. Words and Chinese terms outside a fixed connective vocabulary must appear in the cited values or field labels, and names in ownership or naming phrases must match a recorded value as a whole. The check is literal support, not semantic entailment: a negation or reordering built only from recorded words and connectives can still pass, so the model prompt also forbids inference beyond the facts.

句子必须引用本章至少一条存在的事实。数字规范化后须等于被引用事实中的某个值：千分位、全角数字、小数或科学计数法、中英文数词均可；数字还按含义匹配：百分比只能对应比例类事实（`0.983` 写成 `98.3%`）或已记录的百分比，不能对应计数、分值、字节数或普通数字，例如 `50%` 不能引用文件数 50；带单位的数字（个、条、字节、分、秒、币种或日期部分）须对应同一单位的事实或未定类型的数字，例如 `4,815,739个文件` 不能引用字节总数；不带单位的数字可对应任一被引用的值。记录文本中的数字按其上下文定类型，所以 `200 generated images` 可支持 `200张图片`；时间戳中的时分按日期部分处理。日期按自然日比较，支持 ISO、斜杠、中文和英文月份写法。固定连接词表以外的英文单词和中文词须出现在被引用事实的取值或字段标签中，负责人、名称等语境中的名称须与记录值整体一致。校验是字面支持检查，不做语义蕴含判断：只用已记录词语和连接词组成的否定或重排仍可能通过，因此模型提示词同时禁止超出事实的推断。

