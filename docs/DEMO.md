# 十分钟导览

[English](DEMO.en.md) · [返回首页](../README.zh.md)

`uv run datakeel demo` 会生成本地样本、证据与业务数据，并启动 API 和 worker。下面从一个全新的 `DATAKEEL_HOME` 开始，使用隔离端口与 fake 模型；不需要数据库服务、对象存储或模型密钥。

首次使用先在仓库根目录执行 `uv sync --locked` 安装依赖，然后复制这一行启动。端口 `8773` 必须空闲；如果已占用，换一个空闲端口，并同步替换后文 URL。

```bash
DATAKEEL_HOME=$(mktemp -d) uv run datakeel demo --port 8773
```

打开 <http://127.0.0.1:8773/>，选择中文、浅色主题，等待初始化任务完成。截图使用生成数据；对象 ID 和时间每次会变化。以下流程会修改这个临时工作区。完成后在启动终端按 Ctrl+C 停止服务；重新演练时再次运行上面的命令，使用新的临时目录。

## 如果你本机已有配置

如果之前设置过 `DATAKEEL_*` 环境变量，请用下面的隔离启动方式替代上一行。它清除已有数据库、存储与模型设置，并为这次导览创建新的临时目录。仅保留显式设置的沙箱镜像和运行时端点，强制使用 `container` 并关闭开发子进程后端。演练第 11 节时，须先构建镜像、导出摘要，再运行此启动器。

```bash
uv run python - <<'PY'
import os
import subprocess
import tempfile

sandbox_keys = {"DATAKEEL_SANDBOX_IMAGE", "DATAKEEL_SANDBOX_DOCKER_HOST"}
environment = {
    key: value for key, value in os.environ.items()
    if not key.startswith("DATAKEEL_") or key in sandbox_keys
}
environment["DATAKEEL_SANDBOX_BACKEND"] = "container"
environment["DATAKEEL_SANDBOX_ALLOW_SUBPROCESS"] = "false"
environment["DATAKEEL_HOME"] = tempfile.mkdtemp(prefix="datakeel-tour-")
environment["DATAKEEL_BASE_URL"] = "http://127.0.0.1:8773"
subprocess.run(
    ["uv", "run", "datakeel", "demo", "--port", "8773"],
    env=environment,
    check=True,
)
PY
```

## 1. 工作台：从状态找到对象（约 30 秒）

打开「工作台」，确认运行中流水线已经归零，查看审批待办、最近动作与质量告警。最近动作可以继续打开，不必记住 ID。

![工作台展示已清空的运行队列和最近动作](images/demo/01-workbench.jpg)

## 2. 审一个样本，再生成版本（约 2 分钟）

打开「证据」，确认「证据数据集」为 `Paired scenes · evidence demo`，点击「查找行人标注缺口」。翻页找到并打开 `val/scene-0817/image.png`。抽屉把图片、caption、标注与证据矩阵放在一起；未知证据和已测得的缺失会分别显示。

![样本详情顶部的原图、caption 和证据矩阵](images/demo/02a-evidence-overview.jpg)

在 `mentions` 行人断言卡上点击「定位证据」，查看 caption 中对应片段，再点击「接受断言」。人工决定保留独立记录，原始提取证据仍可追溯。

![定位并接受 mentions 断言后的审阅状态](images/demo/02-evidence-review.jpg)

按 Esc 关闭抽屉，勾选这个样本，点击「生成版本」。到「数据库」打开该数据集的「版本」页：新版本只有选中的一个文件，旧版本仍保留完整清单。

![数据集版本页展示新生成的单文件版本](images/demo/03-created-version.jpg)

## 3. Agent 提议删除，由人签批（约 2 分钟）

打开「智能体对话」（Agent），新会话的数据集选 `Paired scenes · evidence demo`；展开「会话预算」，把词元上限设为 `1000000`，再点「新建会话」。此演示使用本地 `fake-demo`，预算只是执行上限，不会调用付费模型。

依次发送：

```text
查找 val 中 caption 提到行人、没有行人标注并且与 train 近重复的证据样本
```

```text
删除这些样本
```

第二条消息生成待签批计划。此次 fake 会话只选查询命中的最多两条样本，和上一步单独审阅的 `scene-0817` 不是同一个选择集；以计划中的对象清单为准。此时尚未执行删除。

![Agent 查询证据后展示待签批的删除计划](images/demo/04-agent-proposal.jpg)

打开「审批待办」，核对对象、影响范围、不可逆提示和计划摘要，再点击「签批并删除文件」。签批绑定这份冻结的计划，不能挪给另一组参数。

![审批单展示影响对象、不可逆提示和计划摘要](images/demo/05-approval-sheet.jpg)

执行成功后点「查看血缘回执」。关系页把动作、回执事件和受影响对象连起来；可以从结果继续追溯发生了什么。

![执行回执的关系页](images/demo/06-receipt-relations.jpg)

## 4. 从数据目录理解一个数字（约 1 分钟）

打开「数据目录」，展开 `ecommerce`，选择 `ecommerce/main/orders`，点击 `paid_amount` 的「下游影响」。能看到 `retail_revenue` 依赖这个金额字段，业务口径有明确来源。

![paid_amount 字段的下游指标依赖](images/demo/07-catalog.jpg)

## 5. 问数：答复、澄清、答不了（约 2 分钟）

打开「问数」，保留演示的参考日期 `2026-10-01`，依次试三种问题。

1. 输入「上个季度华东区零售额是多少」，点击「开始问数」。得到 `4,979,475`，同时显示指标版本 1、来源、过滤口径和查询证据。
2. 改问「上个季度营业额是多少」。营业额对应不止一种定义，页面先列出候选口径，不给猜测数字。点击一个候选后才继续回答。
3. 重新打开「问数」，输入「下个月零售额是多少」。当前时间解析器不支持这个时间条件，页面明确显示无法回答，并保留登记口径，不执行查询。退货率等未登记概念可能返回受保护的候选指标，需要先申请后才能披露。

![可追溯的问数答复](images/demo/08-ask-answer.jpg)

![含糊问题先澄清业务口径](images/demo/09-ask-clarification.jpg)

![时间条件不受支持时明确无法回答](images/demo/10-ask-unanswerable.jpg)

## 6. 修改指标，再回滚定义（约 2 分钟）

回到「数据目录」→「指标目录」，打开 `retail_revenue`，点击「修改定义」。将「金额或计数字段」从 `paid_amount` 改为 `ecommerce/main/orders/list_amount`，点击「审阅修改」，核对可逆计划后点「执行动作」。

![指标修改的可逆计划](images/demo/11-metric-plan.jpg)

回到「问数」，重问「上个季度华东区零售额是多少」。答案变成 `5,255,975`，指标版本升到 2；数字变化对应明确的口径变化。

![指标版本 2 使用 list_amount 后的答案](images/demo/12-metric-updated.jpg)

回到「数据目录」→「指标目录」，再次选择 `retail_revenue`，点击「打开对象」，再选择对象页的「历史」。在版本 1 旁点击「回滚到此版本」。签批单会显示一个受影响指标「零售额」和当前版本 2 → 执行后版本 3；确认可逆计划后，点击「执行动作」。页面会刷新到版本 3，版本 1 和版本 2 仍保留在历史中。

![指标回滚签批单展示版本 2 到版本 3 的变化](images/demo/12a-metric-rollback-plan.jpg)

回到「问数」，输入「上个季度华东区零售额是多少」，再次点击「开始问数」：答案恢复为 `4,979,475`，当前指标版本为 3。版本递增说明回滚本身也是一次可审计动作。

![回滚后的指标版本 3 与恢复的答案](images/demo/13-metric-restored.jpg)

## 7. 用 ⌘K / Ctrl+K 找回对象（约 30 秒）

按 ⌘K（macOS）或 Ctrl+K，输入 `retail_revenue`。选择「零售额」后按 Enter，直接回到指标对象页。

![命令面板按指标 ID 搜索对象](images/demo/14-command-palette.jpg)

## 8. 跑一次低质样本清理并签批（约 1 分钟）

先在第二个终端执行以下导入命令，新建独立的 `Workflow cleanup demo`：两个空文本加一个正常文本。它不改变原有 400 文件数据集，清理也只选择这个新数据集。

```bash
curl --fail http://127.0.0.1:8773/api/datasets \
  -H 'Content-Type: application/json' --data-binary @- <<'JSON'
{
  "name": "Workflow cleanup demo",
  "files": [
    {"filename": "empty-a.txt", "content_base64": ""},
    {"filename": "empty-b.txt", "content_base64": ""},
    {"filename": "observation.txt", "content_base64": "QSBnZW5lcmF0ZWQgb2JzZXJ2YXRpb24gd2l0aCBlbm91Z2ggdGV4dCB0byBiZSB1c2VmdWwu"}
  ]
}
JSON
```

刷新浏览器，打开「工作流」→「低质样本清理」。数据集选 `Workflow cleanup demo`，保留质量分数上限 `60`，点击「运行工作流」。时间线显示查找、自动隔离及删除待签批；此时三个文件仍在，两个空文件已被隔离。

![低质样本清理自动隔离后暂停等待签批](images/demo/15-workflow-paused.jpg)

点击「查看签批」，确认冻结计划只影响两个空文件，再点「签批并删除文件」。点击「返回工作流」：运行仍然暂停。点击「签批后继续」，工作流复用已有删除回执并完成质量复查，最终只剩 `observation.txt`。刷新页面后，运行记录与时间线仍保留。

![显式恢复后的工作流结论与完成状态](images/demo/16-workflow-complete.jpg)

其他工作流可从同一入口选择。Agent 的「按工作流运行」建议只预填数据集并打开表单，不自动执行。定义、CLI、失败语义及接口见[工作流参考](WORKFLOWS.md)。

## 9. 添加并删除一条记忆（约 1 分钟）

打开「记忆」，添加全局条目 `Catalog reports use the approved active-record definition.`。在新的 Agent 会话里输入 `How do catalog reports use active records?`，查看「本轮取用记忆」与来源。此处验证实际取用标记；离线演示的固定答复不代表模型理解记忆内容。

回到记忆面板，删除刚添加的条目并确认。再新建会话问同一句话，确认不再显示该条记忆；历史引用会显示为已删除。也可输入 `委派目录分析`，展开子 Agent 步骤查看工具和 token。[Agent 参考](AGENT.md) 解释检索条件及删除范围。

## 10. 拒绝一条待复核关系（约 1 分钟）

打开「知识图谱」，选择 **Business notes · knowledge graph demo**，在「查找实体」输入 `Vivo`，点击「查看关系证据」。抽屉高亮证据句，并明确提示尾实体未能在原文定位。这条录制中的候选仍保留供人工复核。

![录制关系的原文证据与缺失尾实体](images/demo/19-kg-source.jpg)

关闭抽屉，勾选该关系，点击「拒绝所选」，切到「图视图」。确认这条边显示为红色虚线「已拒绝」，原文核对仍为「待复核」。「抽取记录」可查看故意截断的失败块，「Schema 提案」列出被过滤的候选；三篇长文明确标注为 fake 脚本来源，不是真实模型输出。

![拒绝后的图边保留独立的核对状态](images/demo/20-kg-rejected.jpg)

Schema 配置、离线评测及外发签批边界详见[知识图谱参考](KG.md)。

## 11. 写一个算子，审阅后在沙箱运行（约 3 分钟）

本节另需自行安装的 Docker 兼容运行时。先按[容器配置](CUSTOM_OPERATORS.md#container-setup--容器配置)构建镜像并设置 `DATAKEEL_SANDBOX_IMAGE`，再用相同环境启动本次临时 demo。全程只用下面生成的文本，不需要模型或外部数据。

在第二个终端创建独立的三行文本数据集：

```bash
curl --fail http://127.0.0.1:8773/api/datasets \
  -H 'Content-Type: application/json' --data-binary @- <<'JSON'
{
  "name": "Custom operator demo",
  "files": [
    {"filename": "lines.txt", "content_base64": "a2VlcCBmaXJzdApkaXNjYXJkIHNlY29uZAprZWVwIHRoaXJkCg=="}
  ]
}
JSON
```

打开仓库的 [filter_lines.py](../examples/custom_operators/filter_lines.py)，读完后复制整个文件。刷新浏览器，打开「自定义算子」，名称填 `filter_lines`、模态选「文本」，粘贴完整代码后点「提交代码审阅」。签批单直接展示完整代码、代码 SHA-256 和静态检查；逐行核对后点「签批并注册自定义算子代码」。静态检查未命中不代表安全，隔离仍由容器提供。

在「已批准版本」选 `Custom operator demo`，参数填 `{"contains":"keep"}`，点「在算子链中运行」。等待 worker 后刷新，确认沙箱记录成功、退出原因及实际镜像摘要。到「数据库」打开该数据集的「关系」，查看本次自定义算子血缘事件，核对 `code_hash` 等于签批时的完整哈希，同时查看参数摘要和资源用量。输出的 `filtered-0.txt` 保留 `keep first`、`keep third` 两行。

在源码末尾添加一行注释并重新提交，确认新签批单的哈希发生变化，原批准版本仍保留；新代码只有再次签批后才可运行。第二个示例 [tag_images.py](../examples/custom_operators/tag_images.py) 使用 `{"label":"generated-fixture"}` 给生成图片附标签。完整文件合同、CLI、输出校验和不防什么见[自定义算子说明](CUSTOM_OPERATORS.md)。本节不包含在下方既有截图回放脚本中。

## 12. 对比版本、发布并核对交付（约 2 分钟）

回到 **证据**，选择第 2 步使用的配对样本数据集，再次查找行人标注缺口。勾选一个样本后点击 **生成版本**；清空勾选，重新选中同一个样本，再加选另一个样本，生成第二个版本。这是两份独立冻结的选择。在 **数据库 → 数据集 → 版本** 中按实际 ID 找到它们。

将单文件版本选作 **基准版本**，双文件版本选作 **目标版本**，点击 **对比版本**。查看 **新增、删除、内容变更、仅元数据变更、未变** 五类，以及标注、质量分和证据决策摘要。本次选择自然展示新增和未变，其余分类可以是零。

展开 **发布版本**，选择双文件版本，填入标签 `v1.0.0` 和说明 `已审阅的生成样本`。点击 **审阅发布计划**，检查来源版本及冻结的文件影响后，点击 **签批并发布版本**。在 **发布记录** 展开 `v1.0.0`，点击 **导出交付包**，将下载保存为 `delivery.tar.gz`。

在已安装 Datakeel 的终端执行 `datakeel reconcile delivery.tar.gz --manifest MANIFEST.json`。六类全部通过，命令无须连接演示服务。按 [交付说明](RELEASES.zh.md#导出与离线对账) 的代码解压副本并修改一个文件字节，再执行 `datakeel reconcile received --manifest MANIFEST.json`，**内容哈希** 会指出损坏文件，命令退出码非零。回到发布详情点击 **核对存储对象**，刷新后仍能查看六类存档报告；平台中的原始对象未被改坏，因此检查仍通过。

本节是下方截图重放之后可单独操作的导览，只修改生成的工作区和下载副本。清单、收货记录、API 及 CLI 说明见 [交付说明](RELEASES.zh.md)。

## 13. 确认字段标准，再查看落标情况（约 1 分钟）

打开「数据标准」→「字段标准」，搜索 `customer_id`，查看中英文业务含义、数据类型、负责人和状态；切到「码表」查看码值含义。每次修改都先显示冻结计划，签批后才生效。

切到「映射建议」，搜索某列，阅读候选标准的名称、类型和值域打分理由。点击「审阅映射」，检查字段与目标标准，点「签批并确认标准映射」后才保存。低分列明确显示不建议；已经确认的列保留当前标准。

切到「覆盖率」，依次按数据库、表、负责人查看已映射比例、映射字段合规率与违规 Top N。打开表或字段链接，在对象「事实」中展开落标检查，可看到失败规则、违规条数和脱敏样例。最后打开「落标报告」，查看字段质量和规则报告。「变更历史」支持准备恢复旧修订的签批计划。

演示包含单独生成的合规表与故意违规表。如果使用旧工作区尚未生成标准演示，在同一个 `DATAKEEL_HOME` 下执行 `uv run datakeel standards demo` 后刷新。详见[数据标准参考](STANDARDS.md)。此流程完全基于规则，不需要模型。

## 14. 创建一条表规则并跟踪恢复（约 2 分钟）

打开「质量规则」→「新建规则」。ID 填 `tour_orders_amount`，名称填「订单实付金额非负」，数据源 ID 填 `ecommerce`，Schema 填 `main`，表名填 `orders`，列名填 `paid_amount`。选择「范围」，参数保持 `{"minimum": 0}`，阈值填 `0`，负责人填 `commerce-team`，计划留空。演示订单表有 18,000 行，将「扫描行数上限」显式设为 `20000`；默认的 `10000` 会如实报告超出预算。点击「审阅修改」，核对冻结定义后点「签批并新建质量规则」。

在列表选择这条规则，点「立即运行」，再在计划中点「执行动作」。任务由 demo worker 执行，最近结果会在五秒刷新周期内显示「通过」。点「编辑规则」，把参数改为 `{"minimum": 1000000000000}`，审阅并签批修改后再运行。生成样例中的金额均低于这个下界，结果显示「失败」，问题单显示「打开」。输入认领人，点「认领问题」，审阅后执行。重复运行只增加当前问题单的失败次数。

把参数改回 `{"minimum": 0}`，签批修改并运行。问题单变为「已恢复待确认」；点「确认解决」并执行计划后才关闭。最近结果保留各次观测，趋势线区分实际值与阈值。到「数据目录」打开 `ecommerce/main/orders` 的对象页，可以看到相关规则及状态。规则换版时，最近状态只使用当前版本结果，旧结果仍保留。

YAML、UTC cron、超时与扫描上限、基线、签名告警和评分约定见[质量规则参考](QUALITY_RULES.md)。这一节为手动扩展导览，下面的自动截图脚本仍覆盖原有步骤。

## 15. 看一批标注的质量与抽检（约 1 分钟）

打开数据集 **Aster harbor · annotation quality demo**，切到「标注质量」页签。顶部是三名虚构标注员的一致性：Fleiss κ、Krippendorff α、两两 Cohen κ 与原始一致率，展开可看 K×K 混淆矩阵；下面是框匹配率、平均 IoU 与片段 F1。批次下拉选「Initial harbor annotations」：「抽检验收」显示 AQL 6.5 的已签批拒收记录（样本 8，Ac 1，不合格 2）；「疑似错标」列出 19 条带原因和证据的复核项，可导出返工 JSON/CSV。切回「Reworked harbor annotations」，返工对比显示修正 19、新增 1，抽检不合格项 2 件均已改动。

![标注一致性、抽检历史与返工对比](images/demo/21-annotation-quality.jpg)

指标定义、AQL 表与疑似错标规则见[标注质量参考](ANNOTATION_QA.md)。

## 16. 生成逐句可溯源的说明书（约 2 分钟）

在「数据库」打开 **Paired scenes · evidence demo**，进入「说明书」页签。「数据集版本」选「版本 1」，即带证据断言的导入版本；保持「离线模板」，点「生成草稿」，核对可逆计划后点「执行动作」。七章齐全，动机、用途、分发三章写明「平台中没有这一项的记录」。悬停任一句查看来源事实，点击展开事实 ID、来源对象、字段、取值和记录时间；展开「已删除的句子」，模板生成的句子全部保留。分别下载 Markdown 与 HTML，HTML 中每句话都带依据。

demo 流水线已生成版本 2，因此这份说明书标「已过期」。点「发布说明书」只会准备签批单，签批后才发布。再点「为最新版本重新生成」并执行，然后在「与历史说明书对比」选版本 1 的说明书：「两份说明书的差异」列出变化的章节与事实，下面并排显示两份说明书。想在没有密钥的情况下试模型路径，可选「已配置模型」+「离线 fake」，任务进入「运行记录」，完成后点「刷新说明书」。最后打开 **Images and diagrams · knowledge graph demo**，选择中文生成，查看引用图谱实体的说明书。引用和模型边界详见[说明书参考](DATASHEETS.md)。本节为手动导览，下面的截图回放覆盖前面各节，`npm run smoke:ui` 会自动走一遍本节。

## 17. 检查并清洗训练记录（约 2 分钟）

先导入独立生成的 JSONL：一条合法对话、它的完全重复、chosen/rejected 相同的偏好对，以及含保留样例地址 `reviewer@example.test` 的记录。将自编的评测题另存为文本文件，导入同一数据集。[训练数据说明](TRAINING_DATA.zh.md)给出支持格式和 HTTP 检查接口；不需要 benchmark 内容或模型。

从「数据库」打开数据集的「文本数据治理」。展开「登记自有评测集」，填名称、勾选已导入评测文件并登记，新评测集自动选中。保留自动格式，点击「检查并试运行清洗」，查看检查计数、语言分布、重复簇与评测命中。「脱敏记录抽样」里邮箱显示为高亮 `[EMAIL]`，坏记录展示文件、行号与删除原因；下载完整逐条清单可看全部保留、删除、脱敏决定。此时数据集仍只有原版本。

切换中文/英文与浅色/深色，检查同一份报告。点击「审阅清洗计划」，核对冻结来源版本和摘要，再「签批并生成清洗后的训练数据版本」。回执可跳转血缘；「版本」保留原清单并新增清洗清单。为已检查版本重新生成离线说明书，可查看有引用的训练测量事实。自动导览会创建独立的七条生成记录，执行这条完整签批链。

## 自动复现与截图

在一个**尚未操作过的新 demo** 上运行以下命令。脚本会按上面的顺序操作真实界面；指标修改和回滚都通过界面准备计划、审阅签批单并执行，直接 API 调用只读取或轮询证据，写入例外仅为创建清理与训练治理使用的独立生成样例。

```bash
npm --prefix web ci
# Linux 上先安装浏览器；macOS 默认使用已安装的 Chrome。
npm --prefix web exec -- playwright install chromium
npm --prefix web run smoke:tour -- http://127.0.0.1:8773
```

脚本生成 25 张 `1440 × 900` 的 JPEG 到 `docs/images/demo/`，每张不超过 400,000 字节，直接取自浏览器，不做图片后处理。`artifacts/demo-tour/tour.json` 记录每步操作、响应状态、对象与版本、图片尺寸及大小、控制台错误和拦截的外部请求；同目录保存页面文本。脚本还检查两种指标签批单的中英文影响数字一致，以及问数结果 `4,979,475 → 5,255,975 → 4,979,475` 和指标版本 `1 → 2 → 3`。新增清理步骤核对两个隔离文件、签批后显式恢复、唯一删除记录、剩余一个文件，以及原 400 文件数据集未变。图谱步骤核对缺失尾实体的原文证据及已保存的拒绝样式；标注质量步骤核对返工批次与 Fleiss κ 已显示。成功要求控制台和页面错误均为 0，外部请求为 0。重复运行需要再次启动全新的临时工作区。

## Knowledge questions / 知识问数

After demo initialization, open Ask data and select the owner, upstream or downstream examples, then enter `shipments 表从哪来？` or `营业额谁负责？` for further questions. The first separates the registered supply-chain role from the candidate document claim about 周岩; the second marks `erp_raw_shipments` as missing from the catalog; the third asks you to choose 销售额 or 零售额.

演示初始化后，在问数页点击负责人例句并作答，再手动输入 shipments 上游、营业额负责人两个问题。第一题把系统角色和文档中周岩的说法分开展示；第二题标明原始表「目录里没有」；第三题请用户选择歧义指标。点击文档说法进入原文关系抽屉。切到知识图谱，选择「企业文档 · Enterprise documents」，打开实体的「对应资产」并接受或拒绝关联。审阅后重问可以看到状态变化；重关联、同版本重抽取仍保留人审。全部来自六篇虚构文档的离线录制，不需要模型密钥。

## 数据资产：发现、申请、使用与审计

默认 demo 通过受控动作发布六个虚构企业资产，覆盖数据集、表、指标与公开/内部/需申请/受限四种分级，不预发授权。

1. 打开「资产市场」，搜索「出货额」或 `Shipment`，按「需申请」与 `enterprise` 标签筛选。进入卡片，查看业务定义、脱敏样例、质量来源、上下游和相关指标。
2. 填写操作人 `analyst`、用途「季度经营分析」、查询范围和未来到期时间，点击「提交申请」。申请列表显示「待审批」。
3. 点击「批准申请」，审阅计划，批准后「确认执行」。Web 审批记为 `local`，申请人不能审批自己的申请，所以第 2 步不要用 `local` 申请。授权记录显示主体、查询范围、期限及授权编号。仅批准计划而不执行不会产生授权。
4. 点击「去问数」，确认操作人 `analyst`，输入「上个季度华东区出货额是多少」，时间基准用 `2026-10-01T00:00:00Z`。拿到登记指标的实际只读查询结果；切换为无授权的操作人会被拒绝并提示申请。
5. 回到资产详情查看「使用审计」，按 `analyst` 筛选，核对 `ask` 入口和授权编号；全局「按人查看全部资产审计」可跨资产查询。
6. 「撤销授权」同样经过计划审批和确认执行。重新问数及重放旧答案都会拒绝。到期也自动失效，无需后台任务。原有审计保留。

「创建资产草稿」可引用既有对象，审阅并执行后上架；编辑或下架也保留修订历史。配置与 API/CLI 详见[数据资产说明](DATA_ASSETS.md)。

## 导入 dbt 与调度元数据

仓库中的虚构 dbt 项目产物可直接导入当前本地工作区：

```sh
uv run datakeel import dbt --source-id shop \
  --manifest tests/fixtures/dbt/manifest.json \
  --catalog tests/fixtures/dbt/catalog.json \
  --run-results tests/fixtures/dbt/run_results.json
```

在目录页选择“导入元数据”。沿用数据库来源 ID，选择本地 `manifest.json`，并按需添加 `catalog.json`、`run_results.json`；点击“导入产物”后查看新增、变更、来源已删除和未变摘要。切换 Airflow 可导入离线 REST v1 DAG JSON。下方“已导入对象”支持筛选 DAG、任务、消费者和指标草稿，打开对象可查看调度、负责人、最近状态、新鲜度及血缘。

指标草稿先留在草稿区。审阅完整定义并生成确认计划后，在签批单中明确签批，才进入语义层。重复导入相同文件应主要显示“未变”；从来源移除的对象保留“来源已删除”标记。CLI、HTTP、文件格式和 OpenLineage 鉴权配置见[元数据导入说明](METADATA_IMPORTS.md)。
