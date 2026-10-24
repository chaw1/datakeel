# 十分钟导览

[English](DEMO.en.md) · [返回首页](../README.zh.md)

`uv run datakeel demo` 会生成本地样本、证据与业务数据，并启动 API 和 worker。下面从一个全新的 `DATAKEEL_HOME` 开始，使用隔离端口与 fake 模型；不需要数据库服务、对象存储或模型密钥。

首次使用先在仓库根目录执行 `uv sync --locked` 安装依赖，然后复制这一行启动。端口 `8773` 必须空闲；如果已占用，换一个空闲端口，并同步替换后文 URL。

```bash
DATAKEEL_HOME=$(mktemp -d) uv run datakeel demo --port 8773
```

打开 <http://127.0.0.1:8773/>，选择中文、浅色主题，等待初始化任务完成。截图使用生成数据；对象 ID 和时间每次会变化。以下流程会修改这个临时工作区。完成后在启动终端按 Ctrl+C 停止服务；重新演练时再次运行上面的命令，使用新的临时目录。

## 如果你本机已有配置

如果之前设置过 `DATAKEEL_*` 环境变量，请用下面的隔离启动方式替代上一行。它清除已有数据库、存储与模型设置，并为这次导览创建新的临时目录。

```bash
uv run python - <<'PY'
import os
import subprocess
import tempfile

environment = {
    key: value for key, value in os.environ.items()
    if not key.startswith("DATAKEEL_")
}
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
3. 重新打开「问数」，输入「退货率为什么上升」。当前目录缺少回答依据，页面明确显示无法回答，并给出相近指标。

![可追溯的问数答复](images/demo/08-ask-answer.jpg)

![含糊问题先澄清业务口径](images/demo/09-ask-clarification.jpg)

![超出已注册数据与定义范围的问题明确无法回答](images/demo/10-ask-unanswerable.jpg)

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

## 自动复现与截图

在一个**尚未操作过的新 demo** 上运行以下命令。脚本会按上面的顺序操作真实界面；指标修改和回滚都通过界面准备计划、审阅签批单并执行，直接 API 调用只读取或轮询证据，唯一写入例外是在清理步骤前创建上述独立三文件样例。

```bash
npm --prefix web ci
# Linux 上先安装浏览器；macOS 默认使用已安装的 Chrome。
npm --prefix web exec -- playwright install chromium
npm --prefix web run smoke:tour -- http://127.0.0.1:8773
```

脚本生成 20 张 `1440 × 900` 的 JPEG 到 `docs/images/demo/`，每张不超过 400,000 字节，直接取自浏览器，不做图片后处理。`artifacts/demo-tour/tour.json` 记录每步操作、响应状态、对象与版本、图片尺寸及大小、控制台错误和拦截的外部请求；同目录保存页面文本。脚本还检查两种指标签批单的中英文影响数字一致，以及问数结果 `4,979,475 → 5,255,975 → 4,979,475` 和指标版本 `1 → 2 → 3`。新增清理步骤核对两个隔离文件、签批后显式恢复、唯一删除记录、剩余一个文件，以及原 400 文件数据集未变。图谱步骤核对缺失尾实体的原文证据及已保存的拒绝样式。成功要求控制台和页面错误均为 0，外部请求为 0。重复运行需要再次启动全新的临时工作区。
