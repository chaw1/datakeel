import assert from "node:assert/strict";

import {
  openMetric,
  rollbackMetric,
  verifyMetricPlan,
} from "./demo-tour-metrics.mjs";

export async function enterpriseTour({ page, base, capture, report }) {
  const question = "上个季度华东区零售额是多少";
  async function ask(value) {
    await page
      .getByRole("textbox", { name: "业务问题", exact: true })
      .fill(value);
    const pending = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/ask" &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "开始问数", exact: true }).click();
    const response = await pending;
    assert.equal(response.status(), 200);
    const answer = await response.json();
    await page.locator(`.ask-answer-${answer.status}`).waitFor();
    return answer;
  }
  await page.goto(`${base.origin}/#/catalog`);
  await page
    .locator(".catalog-source-tree button")
    .filter({ has: page.getByText("ecommerce", { exact: true }) })
    .click();
  await page
    .locator(".catalog-nested-tables button")
    .filter({ has: page.getByText("ecommerce/main/orders", { exact: true }) })
    .click();
  await page
    .getByRole("button", { name: "下游影响: paid_amount", exact: true })
    .click();
  await page
    .getByRole("region", { name: "下游影响", exact: true })
    .getByText("retail_revenue", { exact: true })
    .waitFor();
  await capture(
    "07-catalog",
    "数据目录中打开 ecommerce → orders，查看 paid_amount 的下游指标依赖",
    {},
    page.getByRole("region", { name: "下游影响", exact: true }),
  );
  await page.goto(`${base.origin}/#/ask`);
  const original = await ask(question);
  assert.equal(original.status, "answered");
  assert.equal(original.result.rows[0][0], 4979475);
  assert.equal(original.metric_card.definition.version, 1);
  await capture(
    "08-ask-answer",
    "询问上个季度华东区零售额，查看数字、指标版本与来源脚注",
    {
      answerId: original.id,
      value: original.result.rows[0][0],
      metricVersion: original.metric_card.definition.version,
    },
  );
  const ambiguous = await ask("上个季度营业额是多少");
  assert.equal(ambiguous.status, "clarification");
  assert.equal(ambiguous.result, null);
  await capture(
    "09-ask-clarification",
    "询问营业额，查看不同业务口径；系统等待选择而不猜答案",
    { answerId: ambiguous.id, candidateCount: ambiguous.candidates.length },
  );
  const clarified = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/ask" &&
      response.request().method() === "POST",
  );
  await page.locator(".ask-candidate").first().click();
  assert.equal((await (await clarified).json()).status, "answered");
  await page.goto(`${base.origin}/#/ask`);
  const unavailable = await ask("退货率为什么上升");
  assert.equal(unavailable.status, "unanswerable");
  assert.equal(unavailable.sql, null);
  await capture(
    "10-ask-unanswerable",
    "询问退货率上升原因，查看无法回答的边界与相近指标",
    { answerId: unavailable.id, status: unavailable.status },
  );
  await openMetric(page, base);
  await page.getByRole("button", { name: "修改定义", exact: true }).click();
  await page
    .getByRole("combobox", { name: "金额或计数字段", exact: true })
    .selectOption("ecommerce/main/orders/list_amount");
  const prepared = page.waitForResponse((response) =>
    response.url().endsWith("/api/actions/update_metric/prepare"),
  );
  await page.getByRole("button", { name: "审阅修改", exact: true }).click();
  const preparedResponse = await prepared;
  assert.equal(preparedResponse.status(), 200);
  const plan = await preparedResponse.json();
  const sheet = await verifyMetricPlan(page, plan, 1, report);
  await capture(
    "11-metric-plan",
    "将零售额金额字段改为 list_amount，审阅可逆的修改计划",
    { planId: plan.id, fromVersion: original.metric_card.definition.version },
    sheet,
  );
  const executed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${plan.id}/execute`),
  );
  await sheet.getByRole("button", { name: "执行动作", exact: true }).click();
  const executedResponse = await executed;
  assert.equal(executedResponse.status(), 200);
  const run = await executedResponse.json();
  assert.equal(run.status, "SUCCEEDED");
  await page.goto(`${base.origin}/#/ask`);
  const changed = await ask(question);
  assert.equal(changed.result.rows[0][0], 5255975);
  assert.equal(
    changed.metric_card.definition.version,
    original.metric_card.definition.version + 1,
  );
  await capture(
    "12-metric-updated",
    "执行修改后重问同一问题，核对新数字与递增的指标版本",
    {
      runId: run.id,
      answerId: changed.id,
      value: changed.result.rows[0][0],
      metricVersion: changed.metric_card.definition.version,
    },
  );
  const restored = await rollbackMetric({ page, base, capture, report });
  await page.goto(`${base.origin}/#/ask`);
  const afterRollback = await ask(question);
  assert.equal(afterRollback.result.rows[0][0], original.result.rows[0][0]);
  assert.equal(
    afterRollback.metric_card.definition.version,
    original.metric_card.definition.version + 2,
  );
  await capture(
    "13-metric-restored",
    "通过指标历史页准备并执行回滚，再问数验证恢复且历史保留",
    {
      runId: restored.id,
      answerId: afterRollback.id,
      value: afterRollback.result.rows[0][0],
      metricVersion: afterRollback.metric_card.definition.version,
    },
  );
  report.metrics = {
    originalVersion: original.metric_card.definition.version,
    changedVersion: changed.metric_card.definition.version,
    restoredVersion: afterRollback.metric_card.definition.version,
    values: [
      original.result.rows[0][0],
      changed.result.rows[0][0],
      afterRollback.result.rows[0][0],
    ],
    updateRunId: run.id,
    rollbackRunId: restored.id,
  };
}
