# 训练数据治理

[English](TRAINING_DATA.md) · [数据集说明书](DATASHEETS.md) · [演示导览](DEMO.md)

Datakeel 使用本地规则和统计逐条检查已上传的 JSONL。检查就是**试运行**：保存问题与清洗决定，不修改来源数据集。生成清洗版本需要另行准备受控动作并由人签批。全程不需要模型、分词器包、远程 benchmark 或外部服务。

## 支持的记录

按物理行独立解析。坏行记录从 1 开始的行号与原因，后续行继续处理。稳定记录 ID 绑定来源文件 ID、行号和内容哈希。格式可自动识别，也可指定 `messages`、`instruction` 或 `preference`。

```jsonl
{"messages":[{"role":"user","content":"描述一幅虚构港口场景。"},{"role":"assistant","content":"小船驶向空旷的码头。"}]}
{"instruction":"把 boat 翻译成中文。","input":"","output":"船"}
{"prompt":"简短问候。","chosen":"你好！","rejected":"你好你好你好你好。"}
```

对话支持开头的 system 和工具交互。偏好对的 `chosen`、`rejected` 也接受对话数组。空内容、角色或顺序错误、末轮非 assistant 都会报告。内容始终是不可信数据，规则不执行内容中的指令。

## 导入生成样例

在隔离的本地 demo 已运行于 8773 端口时，以下标准库命令导入六条生成记录（含坏行）和独立评测文件，并打印数据集 ID。本地 API 使用其他端口时修改回环地址。

```bash
uv run python - <<'PYTHON'
import base64
import json
from urllib.request import Request, urlopen

question = "Why does the fictional silver observatory keep a separate written weather log beside its northern telescope during every evening shift?"
conversation = {"messages": [
    {"role": "user", "content": "Describe a quiet fictional harbor at sunrise."},
    {"role": "assistant", "content": "A small boat rests beside an empty pier while sunlight reaches the water."},
]}
records = [conversation, conversation,
    {"instruction": "Where should the generated report go?", "input": "", "output": "Send it to reviewer@example.test for review."},
    {"prompt": "Choose a greeting.", "chosen": "Welcome to the garden.", "rejected": "Welcome to the garden."},
    {"messages": [{"role": "user", "content": question}, {"role": "assistant", "content": "The independent log helps compare conditions across shifts."}]},
]
source = "\n".join(json.dumps(record) for record in records) + "\n{broken json\n"
def encoded(text):
    return base64.b64encode(text.encode()).decode()
body = {"name": "Generated training governance demo", "files": [
    {"filename": "training.jsonl", "content_base64": encoded(source)},
    {"filename": "evaluation.txt", "content_base64": encoded(question + "\n")},
]}
request = Request("http://127.0.0.1:8773/api/datasets", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
with urlopen(request, timeout=30) as response:
    print(response.read().decode())
PYTHON
```

## 在数据集页面操作

从「数据库」打开数据集，进入「文本数据治理」。选择来源版本、记录格式、估算词元上限与污染检查 n-gram 大小。展开区域只读取已保存报告；点击「检查并试运行清洗」才开始本地扫描。

报告包括逐规则受影响记录数、解析数与总数、中英混合及不确定语言分布、置信度、逐文件汇总、重复与近重复组、评测命中和偏好对长度偏置。不同规则可能命中同一条记录，不能把各规则计数相加当成独立记录数。语言百分比以全部检查记录为分母，含坏行时加总可能不足 100%。

抽样记录展示文件和行号、稳定 ID、脱敏预览、逐条决定与原因。高亮证据及原字段偏移量用于定位问题，不显示检测出的个人值或密钥。抽样、重复组和污染命中受 `sample_limit` 限制，默认 50、最多 200。「下载完整逐条决定清单」导出包含所有保留、删除和脱敏决定的 JSONL，旁边展示 SHA-256。报告脱敏不改写原始上传文件；原文件仍遵循原有访问与下载方式。

### 登记自有评测集

先把自己的评测题导入为 `.jsonl` 或 `.txt` 文件。在「登记自有评测集」填写名称，选择当前数据集已导入的文件，登记固定版本快照。检查前勾选需要对照的评测集。同数据集里选作评测的文件自动排除出训练扫描。API 也支持引用另一个已存在数据集的评测文件。

污染检查使用可配置的 n-gram 重叠，默认 13，并结合规范化包含和保守模糊匹配识别轻改题目。命中报告指向用户登记的评测条目。仓库不捆绑任何 benchmark 题目。未选择评测集时，没有污染命中只表示没有执行对照。

### 签批清洗

审阅「清洗试运行报告」、逐条决定及完整清单，点击「审阅清洗计划」。计划绑定本次检查及冻结来源；核对版本、影响对象和摘要后，只有「签批并生成清洗后的训练数据版本」才会执行。拒绝或过期不改变数据集。切换来源、报告或配置会清除当前展示的计划。

清洗采用确定性策略：

- 删除坏格式、超长行、结构错误、必填内容为空、词元超限、代码块未闭合、完全或近重复、无有效区分的偏好答案及评测污染记录。
- 其余含 PII 或密钥的记录使用 `[EMAIL]`、`[PHONE]`、`[BANK_CARD]` 等带类型占位符脱敏。存在阻断问题时优先删除。
- 保留其他记录。模板套话、重复率、乱码、HTML/URL 残留、短答案、同题不同答和可选安全词命中只作为审阅信号，单独命中不会删除记录。

执行前重新读取来源与评测字节，复现决定并验证哈希，然后发布 `.clean.jsonl` 到新的不可变版本清单；旧版本保留。一次试运行只能生成一次清洗版本。血缘连接来源、结果版本与完整逐条决定清单，记录计数、原因和冻结配置。重复记录保留的代表由冻结的文件和记录顺序决定。

## 信号与配置

| 检查       | 含义与边界                                                                                                                                       |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 结构       | system 位于开头；对话角色、工具交互和末轮 assistant 合法；空字段、代码围栏闭合与行字节上限。                                                     |
| 长度       | 确定性的字符及词语估算，不是模型分词或计费词元；默认上限 8192。                                                                                  |
| 语言       | 文字体系比例与常用词区分中文、英文、混合和不确定，并给置信度；短文或特殊文本可能不确定。                                                         |
| 质量       | 重复 trigram、中英可配置模板词、控制符/替换符/乱码模式、HTML/URL 与异常短答案，均需复核。                                                        |
| 去重       | 规范化哈希识别完全重复；磁盘候选索引与文本相似度识别近重复，安装后复用可选 Rust 哈希比较器；不做全语料两两比较。                                 |
| 同题不同答 | 相同规范化 prompt 配不同回答时单独标记，不直接等同重复。                                                                                         |
| PII 与密钥 | 邮箱、中国大陆及国际电话、校验位正确的身份证、Luhn 正确的银行卡、IP、可识别的密钥/令牌与带凭证 URL。校验错误的号码不会按有效身份证或银行卡报告。 |
| 偏好对     | chosen 为空、两答案完全或近似相同，以及 chosen 长于 rejected 的比例。                                                                            |
| 安全       | 可配置词表，默认仅含中英窃取凭证短语，可用空表关闭。明确是**规则粗筛**，不代表安全认证或语义判断。                                               |

近重复候选使用 8 个 MinHash 分带，每带最多 8 个候选，每条记录最多比较 64 个候选。保留首个可保留的原始代表；报告中的重复样例是有上限的「代表—记录」组，不是穷举的传递闭包聚类。候选上限限制了工作量与内存，也可能漏掉密集或特殊语料中的匹配。相近措辞可能表达不同含义，删除前应人工审阅；规则不保证答案的语义质量。

共享 `text.pii_redact` 算子保留原有 `emails`、`phones`、`replacement` 参数 schema。默认字面值 `replacement="[REDACTED]"` 现在选择带类型占位符；其他自定义 replacement 原样使用。邮箱和电话开关仍有效。表格 PII 推断和显式记忆写入复用同一检测器及有效号码校验。

报告冻结全部阈值与词表。HTTP 的 `config` 支持 `format`、`max_tokens`、`near_distance`、`near_similarity`、`repetition_threshold`、`refusal_phrases`、`safety_terms`、`contamination_ngram`、`contamination_threshold`、`sample_limit`、`max_line_bytes`。Web 暴露常用选项，其余通过 HTTP 设置。过小 n-gram 或过松阈值可能增加误报，清洗前先审阅逐条清单。

## 质量分与说明书

记录的训练信号进入既有五维评分，维度权重不变。完整性、一致性、唯一性由相应受影响记录比例设置分数上限；标注和分布维持既有行为。没有训练检查证据的数据集（包括纯图片数据集）维持原分数。

为已检查版本生成说明书时，增加语言分布、去重率、PII 记录数、污染率、格式错误率、记录数与规则版本等测量事实。比例与计数保留类型和单位，经原有引用及数字校验器检查。检查或清洗后须重新生成说明书，已保存正文不会改写。详见[说明书参考](DATASHEETS.md)。

## HTTP、CLI 和 Agent

将下列 ID 替换成你本地工作区已上传的对象。`DATAKEEL_URL` 是本地 API 地址。

```bash
DATAKEEL_URL=http://127.0.0.1:8773
curl --fail "$DATAKEEL_URL/api/datasets/DATASET_ID/text-governance/evaluations" \
  -H 'Content-Type: application/json' \
  -d '{"name":"自建问题","source_dataset_id":"DATASET_ID","version_id":"VERSION_ID","file_ids":["EVALUATION_FILE_ID"]}'
curl --fail "$DATAKEEL_URL/api/datasets/DATASET_ID/text-governance/analyze" \
  -H 'Content-Type: application/json' \
  -d '{"version_id":"VERSION_ID","evaluation_ids":["EVALUATION_ID"],"config":{"format":"auto","max_tokens":8192,"contamination_ngram":13}}'
curl --fail "$DATAKEEL_URL/api/training-governance/RUN_ID/ledger" -o decisions.jsonl
```

`GET /api/datasets/{dataset_id}/text-governance?version_id=...` 或 `GET /api/training-governance/{run_id}` 读取保存报告。`POST /api/training-governance/{run_id}/clean` 只准备 `ActionPlan`，后续走既有[受控动作审批与执行协议](ACTIONS.md)，不能绕过签批。

```bash
uv run datakeel training-quality DATASET_ID --version-id VERSION_ID
```

CLI 和 Agent 可发现的只读工具 `get_training_quality` 依据真实规则结果回答「这批 SFT 数据有什么问题」，不会发布清洗文件。没有保存报告时，只读路径可以本地计算问题，但不改变版本。报告提供规则证据，不能据此认定训练数据已经正确、合法或完整。
