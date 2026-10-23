import assert from "node:assert/strict";

import { appearance } from "./screenshots-helpers.mjs";

export async function openMetric(page, base) {
  await page.goto(`${base.origin}/#/catalog`);
  await page.getByRole("button", { name: "指标目录", exact: true }).click();
  await page
    .getByRole("region", { name: "指标目录", exact: true })
    .getByRole("button")
    .filter({ hasText: "retail_revenue" })
    .click();
}

export async function verifyMetricPlan(page, plan, fromVersion, report) {
  assert.equal(plan.reversible, true);
  assert.equal(plan.impact.object_count, 1);
  const sheet = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  for (const locale of ["en", "zh"]) {
    await appearance(page, locale, "light");
    const chinese = locale === "zh";
    const impact = chinese ? "1 个对象" : "1 object";
    const title = chinese ? "受影响对象 · 1 个" : "Affected objects · 1";
    const name = chinese ? "零售额" : "Retail revenue";
    const versionChange = `${chinese ? "版本" : "Version"} ${fromVersion} → ${fromVersion + 1}`;
    const objects = sheet.getByRole("region", { name: title, exact: true });
    await objects.getByText(versionChange, { exact: true }).waitFor();
    await sheet.getByText(impact, { exact: true }).waitFor();
    assert.equal(await objects.getByRole("listitem").count(), 1);
    await objects.getByRole("link", { name, exact: true }).waitFor();
    assert.doesNotMatch(await sheet.innerText(), /\b\d+\s*(?:B|KB|MB|GB)\b/);
    assert.doesNotMatch(await page.locator("body").innerText(), /\bP[1-6]\b/);
    await sheet
      .getByRole("button", {
        name: chinese ? "执行动作" : "Execute action",
        exact: true,
      })
      .waitFor();
    (report.metricPlanChecks ??= []).push({
      actionType: plan.action_type,
      planId: plan.id,
      locale,
      impact,
      objectCount: 1,
      metricName: name,
      versionChange,
    });
  }
  return sheet;
}

export async function rollbackMetric({ page, base, capture, report }) {
  await openMetric(page, base);
  await page.getByRole("link", { name: "打开对象", exact: true }).click();
  await page
    .locator(".object-tabs")
    .getByRole("link", { name: "历史", exact: true })
    .click();
  const original = page.locator('[data-metric-version="1"]');
  const current = page.locator('[data-metric-version="2"]');
  for (const locale of ["en", "zh"]) {
    await appearance(page, locale, "light");
    const button =
      locale === "zh" ? "回滚到此版本" : "Roll back to this version";
    await original.getByRole("button", { name: button, exact: true }).waitFor();
    await current
      .getByText(locale === "zh" ? "当前版本" : "Current version", {
        exact: true,
      })
      .waitFor();
    assert.equal(
      await current.getByRole("button", { name: button, exact: true }).count(),
      0,
    );
  }
  const pending = page.waitForResponse((response) =>
    response.url().endsWith("/api/actions/rollback_metric/prepare"),
  );
  await original
    .getByRole("button", { name: "回滚到此版本", exact: true })
    .click();
  const response = await pending;
  assert.equal(response.status(), 200);
  const plan = await response.json();
  assert.equal(plan.action_type, "rollback_metric");
  assert.equal(plan.canonical_params.metric_id, "retail_revenue");
  assert.equal(plan.canonical_params.version, 1);
  const sheet = await verifyMetricPlan(page, plan, 2, report);
  await capture(
    "12a-metric-rollback-plan",
    "在指标对象历史中点击版本 1 的回滚按钮，审阅版本 2 → 3 的可逆签批单",
    { planId: plan.id, sourceVersion: 1, fromVersion: 2, toVersion: 3 },
    sheet,
  );
  const execution = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${plan.id}/execute`),
  );
  await sheet.getByRole("button", { name: "执行动作", exact: true }).click();
  const executed = await execution;
  assert.equal(executed.status(), 200);
  const run = await executed.json();
  assert.equal(run.status, "SUCCEEDED");
  const restored = page.locator('[data-metric-version="3"]');
  await restored.getByText("当前版本", { exact: true }).waitFor();
  assert.equal(await restored.getByRole("button").count(), 0);
  for (const version of [original, current])
    await version
      .getByRole("button", { name: "回滚到此版本", exact: true })
      .waitFor();
  report.rollbackHistory = {
    versions: [1, 2, 3],
    currentVersion: 3,
    sourceVersion: 1,
    via: "ui",
  };
  return run;
}
