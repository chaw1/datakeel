// Verify bilingual workflow summaries against a fresh, generated loopback demo.
// node scripts/workflow-presentation.mjs http://127.0.0.1:8773 output-directory
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { URLSearchParams } from "node:url";

import { chromium } from "playwright";

import { appearance, localBase, settle } from "./screenshots-helpers.mjs";
import {
  cleanupFixture,
  workflowJourney,
  workflowRoutingSmoke,
} from "./workflow-smoke.mjs";

const base = localBase(process.argv[2]);
assert.ok(process.argv[3], "Use a dedicated output directory");
const output = path.resolve(process.argv[3]);
await mkdir(output, { recursive: true });
const report = {
  startedAt: new Date().toISOString(),
  base: base.origin,
  provider: "fake",
  viewport: { width: 1440, height: 1000 },
  screenshots: [],
  timelines: [],
  modelRows: [],
  errors: [],
  blockedRequests: [],
};
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport: report.viewport,
  timezoneId: "Asia/Shanghai",
  colorScheme: "light",
  reducedMotion: "reduce",
  serviceWorkers: "block",
});
const page = await context.newPage();
page.setDefaultTimeout(30_000);
page.on("pageerror", (error) => report.errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") report.errors.push(message.text());
});
await context.route("**/*", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.origin !== base.origin) {
    report.blockedRequests.push(url.href);
    await route.abort("blockedbyclient");
    return;
  }
  if (
    url.pathname === "/api/agent/conversations" &&
    request.method() === "POST"
  )
    assert.equal(request.postDataJSON().provider, "fake");
  await route.continue();
});

async function json(endpoint, data) {
  const url = new URL(endpoint, base);
  assert.equal(url.origin, base.origin);
  const response =
    data === undefined
      ? await context.request.get(url.href, { maxRedirects: 0 })
      : await context.request.post(url.href, { data, maxRedirects: 0 });
  assert.ok(response.ok(), `${response.status()} ${endpoint}`);
  return response.json();
}

async function capture(name, focus) {
  await settle(page);
  await focus.scrollIntoViewIfNeeded();
  const text = await page.locator("body").innerText();
  await writeFile(path.join(output, `${name}.txt`), text + "\n");
  const bytes = await focus.screenshot({
    path: path.join(output, `${name}.png`),
    animations: "disabled",
  });
  report.screenshots.push({ name, bytes: bytes.length });
  process.stdout.write(`${name}.png\n`);
}

async function captureTimeline(name, runId) {
  const run = await json(`/api/workflows/runs/${runId}`);
  const panel = page.locator(`.workflow-run[data-run-id="${runId}"]`);
  for (const locale of ["zh", "en"]) {
    await appearance(page, locale, "light");
    const summaries = [];
    for (const step of run.steps) {
      const row = panel.locator(`[data-step-id="${step.id}"]`);
      const title = await row
        .locator(".workflow-step-heading strong")
        .innerText();
      assert.notEqual(
        title,
        step.id,
        "A human title precedes the technical ID",
      );
      assert.equal(title, step.title?.[locale]);
      assert.equal(await row.locator("details[open]").count(), 0);
      const summary = await row.locator(".workflow-output-summary").innerText();
      assert.ok(summary.trim(), `${step.id} has a readable summary`);
      assert.doesNotMatch(summary, /[{}]|"function"|"asset_refs"/);
      summaries.push({ id: step.id, title, summary });
    }
    report.timelines.push({ name, locale, runId, summaries });
    await capture(`${name}-${locale}`, panel);
  }
  await appearance(page, "en", "light");
  return run;
}

async function captureAgent(_name, { conversationId }) {
  const saved = await json(`/api/agent/conversations/${conversationId}`);
  const turns = saved.events.filter(
    (event) => event.event === "done" && event.model_routes?.length,
  );
  assert.ok(turns.length > 0);
  assert.ok(turns.some((event) => event.model_routes.length > 1));
  for (const locale of ["zh", "en"]) {
    await appearance(page, locale, "light");
    const rows = page.locator(".model-routing");
    assert.equal(await rows.count(), turns.length, "One compact row per turn");
    assert.equal(await page.locator("details.model-routing").count(), 0);
    const text = await rows.allInnerTexts();
    const dimensions = await rows.evaluateAll((elements) =>
      elements.map((element) => ({
        height: element.getBoundingClientRect().height,
        lineHeight: parseFloat(globalThis.getComputedStyle(element).lineHeight),
      })),
    );
    assert.ok(dimensions.every((row) => row.height <= row.lineHeight * 2));
    report.modelRows.push({
      locale,
      conversationId,
      turns: turns.length,
      text,
      dimensions,
    });
    await capture(
      `agent-compact-${locale}`,
      page.locator(".conversation-main"),
    );
  }
  await appearance(page, "en", "light");
}

async function runWorkflow(id, datasetId) {
  const params = new URLSearchParams({ workflow: id });
  if (datasetId) params.set("dataset", datasetId);
  await page.goto(`${base.origin}/#/workflows?${params}`);
  await page.locator(".workflow-form").waitFor();
  const started = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/workflows/${id}/runs` &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Run workflow", exact: true }).click();
  const response = await started;
  assert.equal(response.status(), 200);
  assert.match(await response.text(), /event: done/);
  const panel = page.locator('.workflow-run[data-run-status="SUCCEEDED"]');
  await panel.waitFor();
  const runId = await panel.getAttribute("data-run-id");
  assert.ok(runId);
  await captureTimeline(id, runId);
  return runId;
}

async function ready() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const tasks = await json("/api/tasks");
    assert.ok(!tasks.some((task) => task.state === "FAILED"));
    if (tasks.length >= 2 && tasks.every((task) => task.state === "COMPLETED"))
      return;
    await delay(500);
  }
  throw new Error("Fresh generated demo did not initialize");
}

try {
  await ready();
  assert.equal((await json("/api/agent/conversations")).length, 0);
  assert.equal(
    (await json("/api/catalog/metrics/retail_revenue")).definition.version,
    1,
  );
  await page.goto(`${base.origin}/#/workflows`);
  await appearance(page, "en", "light");
  report.cleanup = await workflowJourney({
    page,
    base,
    dataset: await cleanupFixture(json),
    json,
    capture: async (name, _action, { runId }) => captureTimeline(name, runId),
  });
  const find = page.locator('.workflow-run [data-step-id="find"]');
  await find.locator("details > summary").click();
  const raw = JSON.parse(await find.locator("pre").innerText());
  const cleanup = await json(`/api/workflows/runs/${report.cleanup.runId}`);
  assert.deepEqual(
    raw,
    cleanup.steps.find((step) => step.id === "find").output,
  );
  await capture("workflow-raw-output-en", find);
  await find.locator("details > summary").click();
  report.healthRunId = await runWorkflow(
    "dataset-health",
    report.cleanup.datasetId,
  );
  report.metricRunId = await runWorkflow("metric-change");
  const comparison = await json(`/api/workflows/runs/${report.metricRunId}`);
  assert.deepEqual(
    comparison.steps.find((step) => step.id === "comparison").output,
    {
      before_rows: [[4979475]],
      after_rows: [[5255975]],
      rows_equal: false,
      impact: comparison.steps.find((step) => step.id === "comparison").output
        .impact,
    },
  );
  report.routing = await workflowRoutingSmoke({
    page,
    base,
    datasetId: report.cleanup.datasetId,
    json,
    capture: captureAgent,
  });
  assert.deepEqual(report.errors, []);
  assert.deepEqual(report.blockedRequests, []);
  assert.equal(report.screenshots.length, 11);
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.failure = error instanceof Error ? error.stack : String(error);
  process.exitCode = 1;
  process.stderr.write(`${report.failure}\n`);
  await page.screenshot({ path: path.join(output, "failure.png") });
} finally {
  report.finishedAt = new Date().toISOString();
  await writeFile(
    path.join(output, "presentation.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser.close();
}
