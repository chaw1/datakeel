// Exercise the documented tour against a fresh, generated loopback demo.
// npm run smoke:tour -- http://127.0.0.1:8773 [images-directory] [report-directory]
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { evidenceTour } from "./demo-tour-evidence.mjs";
import { llmDataJourney } from "./llm-data-smoke.mjs";
import { annotationTour } from "./demo-tour-annotation.mjs";
import { kgTour } from "./demo-tour-kg.mjs";
import { enterpriseTour } from "./demo-tour-enterprise.mjs";
import { cleanupFixture, workflowJourney } from "./workflow-smoke.mjs";
import { appearance, localBase, settle } from "./screenshots-helpers.mjs";

const base = localBase(process.argv[2] ?? "http://127.0.0.1:8773");
const output = path.resolve(
  process.argv[3] ??
    fileURLToPath(new URL("../../docs/images/demo/", import.meta.url)),
);
const reports = path.resolve(
  process.argv[4] ??
    fileURLToPath(new URL("../../artifacts/demo-tour/", import.meta.url)),
);
await mkdir(output, { recursive: true });
await mkdir(reports, { recursive: true });
const manifest = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const viewport = { width: 1440, height: 900 };
const report = {
  startedAt: new Date().toISOString(),
  version: manifest.version,
  base: base.origin,
  viewport,
  locale: "zh",
  theme: "light",
  provider: "fake",
  steps: [],
  screenshots: [],
  requests: [],
  errors: [],
  blockedRequests: [],
};
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport,
  timezoneId: "Asia/Shanghai",
  colorScheme: "light",
  reducedMotion: "reduce",
  serviceWorkers: "block",
});
const page = await context.newPage();
page.setDefaultTimeout(20_000);
page.on("pageerror", (error) =>
  report.errors.push({ kind: "pageerror", message: error.message }),
);
page.on("console", (message) => {
  if (message.type() === "error")
    report.errors.push({ kind: "console", message: message.text() });
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
page.on("response", (response) => {
  const url = new URL(response.url());
  if (url.pathname.startsWith("/api/") && response.request().method() !== "GET")
    report.requests.push({
      method: response.request().method(),
      path: url.pathname,
      status: response.status(),
      via: "ui",
    });
});
async function api(endpoint) {
  const url = new URL(endpoint, base);
  assert.equal(url.origin, base.origin);
  const response = await context.request.get(url.href, { maxRedirects: 0 });
  assert.ok(response.ok(), `${response.status()} ${url.pathname}`);
  report.requests.push({
    method: "GET",
    path: url.pathname,
    status: response.status(),
    via: "api",
  });
  return response.json();
}
async function capture(name, action, evidence = {}, focus) {
  await settle(page);
  if (focus)
    await focus.evaluate((element) =>
      element.scrollIntoView({ block: "start" }),
    );
  const text = await page.locator("body").innerText();
  const privateText = new RegExp(
    "/" +
      "(?:Users/|home/[^/\\s]+)|\\b(?:" +
      ["solar" + "sense", "qa" + "pex", "j" + "lw", "cloud" + "main"].join(
        "|",
      ) +
      ")\\b",
    "i",
  );
  assert.doesNotMatch(
    text,
    privateText,
    "Screenshots contain only public generated data",
  );
  assert.doesNotMatch(text, /\bP[1-6]\b/, "No internal phase labels in the UI");
  const filename = `${name}.jpg`;
  const bytes = await page.screenshot({
    path: path.join(output, filename),
    type: "jpeg",
    quality: 88,
    fullPage: false,
    animations: "disabled",
  });
  assert.ok(
    bytes.length <= 400_000,
    `${filename} exceeds the screenshot size limit`,
  );
  await writeFile(path.join(reports, `${name}.txt`), text + "\n");
  report.steps.push({
    name,
    action,
    route: new URL(page.url()).hash,
    evidence,
  });
  report.screenshots.push({
    filename,
    width: viewport.width,
    height: viewport.height,
    bytes: bytes.length,
  });
  process.stdout.write(`${filename}: ${bytes.length} bytes\n`);
}
async function ready() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const tasks = await api("/api/tasks");
    assert.ok(
      !tasks.some((task) => task.state === "FAILED"),
      "Demo task failed",
    );
    if (tasks.length >= 2 && tasks.every((task) => task.state === "COMPLETED"))
      return tasks;
    await delay(500);
  }
  throw new Error("The fresh generated demo did not finish initializing");
}
try {
  const tasks = await ready();
  const [datasets, conversations, metric] = await Promise.all([
    api("/api/datasets"),
    api("/api/agent/conversations"),
    api("/api/catalog/metrics/retail_revenue"),
  ]);
  assert.equal(
    conversations.length,
    0,
    "Start with a fresh demo home for each tour",
  );
  assert.equal(
    metric.definition.version,
    1,
    "The metric must start with its generated definition",
  );
  const dataset = datasets.find(
    (item) => item.metadata.evidence_samples === true,
  );
  assert.ok(dataset);
  report.fixture = {
    datasetId: dataset.id,
    datasetName: dataset.name,
    completedTaskIds: tasks.map((task) => task.id),
  };
  await page.goto(`${base.origin}/#/workbench`);
  await appearance(page, "zh", "light");
  await page.locator(".workbench-section").first().waitFor();
  await capture("01-workbench", "打开工作台，查看完成的流水线与工作区摘要", {
    completedTasks: tasks.length,
  });
  await evidenceTour({ page, base, dataset, api, capture, report });
  await enterpriseTour({ page, base, capture, report });
  await page.keyboard.press(
    process.platform === "darwin" ? "Meta+k" : "Control+k",
  );
  const search = page.getByRole("combobox", {
    name: "对象名称或 ID",
    exact: true,
  });
  await search.fill("retail_revenue");
  await page
    .getByRole("option")
    .filter({ hasText: "零售额" })
    .first()
    .waitFor();
  await capture(
    "14-command-palette",
    "按 ⌘K 或 Ctrl+K，输入 retail_revenue 搜索对象",
  );
  await search.press("Enter");
  await page.waitForURL((url) =>
    url.hash.startsWith("#/object/metric/retail_revenue"),
  );
  const workflowDataset = await cleanupFixture(async (endpoint, data) => {
    assert.equal(endpoint, "/api/datasets");
    const response = await context.request.post(new URL(endpoint, base).href, {
      data,
      maxRedirects: 0,
    });
    assert.equal(response.status(), 201);
    report.requests.push({
      method: "POST",
      path: endpoint,
      status: response.status(),
      via: "fixture",
    });
    return response.json();
  });
  report.workflows = await workflowJourney({
    page,
    base,
    dataset: workflowDataset,
    json: api,
    capture,
    locale: "zh",
  });
  await kgTour({ page, api, capture, report });
  await annotationTour({ page, base, api, capture, report });
  report.trainingGovernance = await llmDataJourney({
    page,
    base: base.href,
    json: api,
    create: async (data) => {
      const response = await context.request.post(
        new URL("/api/datasets", base).href,
        { data, maxRedirects: 0 },
      );
      assert.equal(response.status(), 201);
      report.requests.push({
        method: "POST",
        path: "/api/datasets",
        status: response.status(),
        via: "fixture",
      });
      return response.json();
    },
    capture: (name, panel) =>
      capture(
        name,
        "登记生成的评测题，检查文本数据治理的脱敏报告及浅深主题",
        {},
        panel,
      ),
  });
  assert.deepEqual(report.blockedRequests, []);
  assert.deepEqual(
    report.errors,
    [],
    "The documented tour must have zero browser errors",
  );
  assert.ok(
    report.requests.every(
      (request) =>
        request.via === "ui" ||
        request.method === "GET" ||
        (request.via === "fixture" && request.path === "/api/datasets"),
    ),
    "Only isolated dataset fixture creation may bypass the UI",
  );
  assert.equal(report.screenshots.length, 25);
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.failure = error instanceof Error ? error.stack : String(error);
  process.exitCode = 1;
  process.stderr.write(`${report.failure}\n`);
} finally {
  report.finishedAt = new Date().toISOString();
  await writeFile(
    path.join(reports, "tour.json"),
    JSON.stringify(report, null, 2) + "\n",
  );
  await browser.close();
}
