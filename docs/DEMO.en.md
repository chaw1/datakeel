# A ten-minute tour

[中文](DEMO.md) · [Back to the README](../README.md)

`uv run datakeel demo` generates local samples, evidence, and business data, then starts the API and worker. This tour uses a fresh `DATAKEEL_HOME`, an isolated port, and the fake model. It needs no database server, object store, or model credentials.

On first use, run `uv sync --locked` from the repository root to install dependencies, then copy this one-line launcher. Port `8773` must be available; if it is occupied, choose a free port and update the URLs below.

```bash
DATAKEEL_HOME=$(mktemp -d) uv run datakeel demo --port 8773
```

Open <http://127.0.0.1:8773/> and wait for both initialization pipelines to finish. The screenshots use **Chinese UI text and the Light theme**; choose 中文 to match them. English labels are included below. All data is generated, and IDs and timestamps vary between runs. The tour changes this temporary workspace. Press Ctrl+C in the launch terminal when finished; use the launcher again for a fresh replay.

## If you already have local configuration

If you previously set `DATAKEEL_*` environment variables, replace the one-line launcher with this isolated launch. It clears inherited database, storage, and model settings and creates a fresh temporary directory for the tour.

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

## 1. Workbench: find the objects behind the status (30 seconds)

Open Workbench (工作台). Confirm that active pipelines have returned to zero, then inspect pending approvals, recent actions, and quality alerts. Recent actions link to their details, so you do not need to remember IDs.

![Workbench with an empty running queue and recent actions](images/demo/01-workbench.jpg)

## 2. Review a sample and create a version (2 minutes)

Open Evidence (证据), confirm that Evidence dataset (证据数据集) is `Paired scenes · evidence demo`, and click Find pedestrian annotation gaps (查找行人标注缺口). Page through the results to find and inspect `val/scene-0817/image.png`. The drawer combines the image, caption, annotations, and assertion matrix. Unknown evidence is distinct from measured absence.

![Sample image, caption, and assertion matrix](images/demo/02a-evidence-overview.jpg)

On the `mentions` assertion for a person, click Locate evidence (定位证据) to highlight its caption anchor, then Accept assertion (接受断言). The decision is recorded separately, preserving the extracted evidence.

![Accepted mentions assertion with its evidence anchors](images/demo/02-evidence-review.jpg)

Press Esc, select this sample, and click Create version (生成版本). Open the dataset from Data library (数据库) and choose Versions (版本). The new version contains the one selected file; earlier manifests remain available.

![Dataset versions including the new single-file selection](images/demo/03-created-version.jpg)

## 3. Let the Agent propose deletion, then approve it (2 minutes)

Open Agent (智能体对话). Select `Paired scenes · evidence demo` for the new conversation, expand the conversation budget (会话预算), set its limit to `1000000`, and create the conversation (新建会话). The local `fake-demo` provider uses no paid model; the budget is an execution limit.

Send these two messages in order. Keep the example questions in Chinese even if you choose the English UI:

```text
查找 val 中 caption 提到行人、没有行人标注并且与 train 近重复的证据样本
```

```text
删除这些样本
```

The first finds validation samples whose captions mention a pedestrian, lack a matching annotation, and have a near duplicate in training. The second requests deletion. The fake conversation selects at most two query matches; this is a different selection from the reviewed `scene-0817`. Check the plan's actual object list. No deletion has executed yet.

![Agent proposes a deletion plan that awaits approval](images/demo/04-agent-proposal.jpg)

Open Approvals (审批待办). Review the objects, impact, irreversible-action notice, and digest, then click Approve and delete files (签批并删除文件). The approval applies to this frozen plan and cannot be reused with changed parameters.

![Approval sheet with affected objects and frozen plan digest](images/demo/05-approval-sheet.jpg)

After execution, open the lineage receipt (查看血缘回执). The relations view connects the action, receipt event, and affected objects so the result can be traced back to its cause.

![Action receipt and object relationships](images/demo/06-receipt-relations.jpg)

## 4. Understand a number through the data catalog (1 minute)

Open Data catalog (数据目录), expand `ecommerce`, and select `ecommerce/main/orders`. Open Downstream impact (下游影响) for `paid_amount`. The view shows that `retail_revenue` depends on this amount field: the business definition has a concrete source.

![Downstream metric dependency of paid_amount](images/demo/07-catalog.jpg)

## 5. Ask: answer, clarify, and decline (2 minutes)

Open Ask (问数), keep the demo reference date `2026-10-01`, and try three questions:

1. Ask `上个季度华东区零售额是多少` (last quarter's East China retail revenue), then submit with 开始问数. The answer is `4,979,475`, with metric version 1, source references, filters, and query evidence.
2. Ask `上个季度营业额是多少` (last quarter's turnover). More than one business definition matches, so the page presents alternatives before calculating. Select a candidate to continue.
3. Reopen Ask and enter `退货率为什么上升` (why the return rate increased). The registered catalog does not support this explanation. The page reports that it cannot answer and offers nearby metrics.

![An answer with traceable sources and metric definition](images/demo/08-ask-answer.jpg)

![An ambiguous business term requires clarification](images/demo/09-ask-clarification.jpg)

![An unsupported question receives an explicit unanswerable result](images/demo/10-ask-unanswerable.jpg)

## 6. Change a metric, then restore its definition (2 minutes)

Return to Data catalog → Metrics (指标目录), open `retail_revenue`, and choose Edit definition (修改定义). Change Amount or count field (金额或计数字段) from `paid_amount` to `ecommerce/main/orders/list_amount`. Click Review change (审阅修改), inspect the reversible plan, then execute it (执行动作).

![Reviewable plan for a reversible metric change](images/demo/11-metric-plan.jpg)

Ask `上个季度华东区零售额是多少` again. The answer becomes `5,255,975` and the metric advances to version 2. The changed number is tied to the changed definition.

![Version 2 answer after switching to list_amount](images/demo/12-metric-updated.jpg)

Return to Data catalog → Metrics, select `retail_revenue` again, click Open object (打开对象), then choose the object page’s History (历史) tab. Beside version 1, click Roll back to this version (回滚到此版本). The approval sheet shows one affected metric, 零售额 (retail revenue), and current version 2 → resulting version 3. Review the reversible plan and click Execute action (执行动作). The page refreshes to version 3, and versions 1 and 2 remain in the history.

![Metric rollback approval sheet showing the transition from version 2 to version 3](images/demo/12a-metric-rollback-plan.jpg)

Return to Ask and enter `上个季度华东区零售额是多少`. Submit the same question again. The answer returns to `4,979,475`, now using version 3. A rollback is itself an auditable change, so the version advances.

![Version 3 restores the original answer while retaining history](images/demo/13-metric-restored.jpg)

## 7. Find the object again with ⌘K / Ctrl+K (30 seconds)

Press ⌘K on macOS or Ctrl+K elsewhere, type `retail_revenue`, select Retail revenue (零售额 in Chinese), and press Enter to open the metric object. In English, the object title, breadcrumb, relationship card and approval sheet use the same name; objects without a translation keep their original names. The Chinese interface retains its existing labels.

![Command palette finding a metric by ID](images/demo/14-command-palette.jpg)

## Replay the tour and generate screenshots

Run this against a **fresh demo that has not been used yet**. The script follows the real UI in the order above. Both metric changes and rollbacks use UI controls to prepare a plan, review the approval sheet, and execute it. Direct API calls only read or poll evidence.

```bash
npm --prefix web ci
# Install Chromium on Linux; macOS uses an installed Chrome by default.
npm --prefix web exec -- playwright install chromium
npm --prefix web run smoke:tour -- http://127.0.0.1:8773
```

The script writes 16 JPEG screenshots at `1440 × 900` to `docs/images/demo/`, each at most 400,000 bytes, directly from the browser without image post-processing. `artifacts/demo-tour/tour.json` records the actions, response status codes, objects and versions, screenshot dimensions and sizes, browser errors, and blocked external requests. Page text is saved beside it. The script also checks consistent impact counts in Chinese and English for both metric plans, the answer sequence `4,979,475 → 5,255,975 → 4,979,475`, and metric versions `1 → 2 → 3`. Success requires zero console or page errors and zero external requests. Start another fresh temporary workspace for every replay.
