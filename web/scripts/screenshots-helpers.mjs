import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

export const fixedTime = "2026-10-01T00:05:00Z";
export const primaryQuestion = "上个季度华东区零售额是多少";
export const viewport = { width: 1440, height: 900 };
export const variants = [
  { locale: "zh", theme: "light" },
  { locale: "zh", theme: "dark" },
  { locale: "en", theme: "light" },
  { locale: "en", theme: "dark" },
];
export const pages = [
  { name: "workbench", hash: "#/workbench", ready: ".workbench-section" },
  { name: "evidence", hash: "#/evidence", ready: ".evidence-sample-row" },
  { name: "knowledge-graph", hash: "#/kg", ready: ".kg-relations tbody tr" },
  { name: "ask", hash: "#/ask", ready: ".ask-composer" },
  { name: "catalog", hash: "#/catalog", ready: ".catalog-object-list button" },
  {
    name: "standards",
    hash: "#/standards",
    ready: ".catalog-object-list button",
  },
  {
    name: "object-table",
    hash: "#/object/table/ecommerce%2Fmain%2Forders?tab=relations",
    ready: ".object-body .graph-node",
  },
  {
    name: "object-metric",
    hash: "#/object/metric/retail_revenue?tab=relations",
    ready: ".object-body .graph-node",
  },
  { name: "approval", hash: "#/approvals", ready: ".approval-sheet" },
  { name: "command-palette", hash: "#/workbench", ready: ".workbench-section" },
  { name: "runs", hash: "#/runs", ready: "main table tbody tr" },
  { name: "workflows", hash: "#/workflows", ready: ".workflow-form" },
  { name: "memory", hash: "#/memory", ready: ".memory-card" },
  { name: "agent-advanced", hash: "#/agent", ready: ".delegation-step" },
];

export function localBase(value) {
  const base = new URL(value);
  assert.equal(
    base.protocol,
    "http:",
    "Screenshots require the local HTTP demo",
  );
  assert.ok(
    ["127.0.0.1", "localhost", "[::1]"].includes(base.hostname),
    "Screenshots may only access loopback",
  );
  assert.equal(
    base.username + base.password,
    "",
    "Credentials are not accepted",
  );
  assert.ok(
    base.pathname === "/" && !base.search && !base.hash,
    "Pass the demo origin without a route or query",
  );
  return base;
}

export function localApi(context, base, writes) {
  async function request(endpoint, data) {
    const url = new URL(endpoint, base);
    assert.equal(url.origin, base.origin);
    if (data !== undefined) {
      assert.equal(
        url.pathname,
        "/api/actions/delete_files/prepare",
        "Only preparation is allowed; never approve or execute",
      );
      writes.push({ method: "POST", url: url.href, phase: "fixture" });
    }
    const response =
      data === undefined
        ? await context.request.get(url.href, { maxRedirects: 0 })
        : await context.request.post(url.href, { data, maxRedirects: 0 });
    assert.ok(
      response.ok(),
      `${endpoint}: HTTP ${response.status()} ${await response.text()}`,
    );
    return response.json();
  }
  return {
    json: (endpoint) => request(endpoint),
    prepare: (data) => request("/api/actions/delete_files/prepare", data),
  };
}

export async function prepareFixture(api) {
  const deadline = Date.now() + 120_000;
  while (true) {
    const tasks = await api.json("/api/tasks");
    assert.ok(
      !tasks.some((task) => task.state === "FAILED"),
      "A demo extraction task failed",
    );
    if (tasks.length && tasks.every((task) => task.state === "COMPLETED"))
      break;
    assert.ok(
      Date.now() < deadline,
      "Demo extraction did not finish within 120 seconds",
    );
    await delay(500);
  }
  const datasets = await api.json("/api/datasets");
  const dataset = datasets.find(
    (item) => item.metadata.evidence_samples === true,
  );
  assert.ok(dataset, "The generated evidence demo is required");
  const [files, pending, table, metric] = await Promise.all([
    api.json(`/api/datasets/${dataset.id}/files`),
    api.json("/api/approvals"),
    api.json("/api/catalog/tables/ecommerce%2Fmain%2Forders"),
    api.json("/api/catalog/metrics/retail_revenue"),
  ]);
  assert.ok(
    table.columns.length > 0 && metric.definition.id === "retail_revenue",
  );
  let plan = pending.find((item) => item.status === "PREPARED");
  const reusedPlan = Boolean(plan);
  if (!plan) {
    const file =
      files.find((item) => item.filename === "val/scene-0817/image.png") ??
      files[0];
    assert.ok(file, "Prepare needs one genuine demo file");
    plan = await api.prepare({
      selection: {
        schema_version: "1.1",
        object_type: "file",
        namespace: "default",
        include_deleted: false,
        dataset_id: dataset.id,
        limit: 1,
        filters: [{ field: "id", operator: "in", value: [file.id] }],
      },
    });
  }
  assert.equal(plan.status, "PREPARED");
  assert.ok(plan.impact.object_count > 0);
  return {
    datasetId: dataset.id,
    datasetName: dataset.name,
    planId: plan.id,
    planAction: plan.action_type,
    reusedPlan,
    fileCount: files.length,
  };
}

export async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForFunction(
    () => !globalThis.document.querySelector(".resource-loading, .ask-loading"),
  );
  await page.evaluate(async () => {
    globalThis.scrollTo(0, 0);
    await new Promise((resolve) => globalThis.requestAnimationFrame(resolve));
    await globalThis.document.fonts.ready;
    const images = Array.from(globalThis.document.images).filter((image) => {
      const box = image.getBoundingClientRect();
      return (
        box.width &&
        box.height &&
        box.top < globalThis.innerHeight &&
        box.bottom > 0
      );
    });
    await Promise.all(images.map((image) => image.decode()));
    await new Promise((resolve) => globalThis.requestAnimationFrame(resolve));
    await new Promise((resolve) => globalThis.requestAnimationFrame(resolve));
  });
  assert.equal(
    await page.locator("main [role=alert]").count(),
    0,
    "No page error banner",
  );
}

export async function appearance(page, locale, theme) {
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption(locale);
  await page
    .getByRole("combobox", { name: /^(Theme|主题)$/ })
    .selectOption(theme);
  await page.emulateMedia({ colorScheme: theme });
  await page.waitForFunction(
    ({ locale, theme }) =>
      globalThis.document.documentElement.lang === locale &&
      globalThis.document.documentElement.dataset.theme === theme &&
      globalThis.localStorage.getItem("datakeel.locale") === locale &&
      globalThis.localStorage.getItem("dk-theme") === theme,
    { locale, theme },
  );
}

async function palette(page) {
  return page.locator("html").evaluate((element) => {
    const style = globalThis.getComputedStyle(element);
    return Object.fromEntries(
      [
        "paper",
        "sheet",
        "ink",
        "muted",
        "rule",
        "pencil",
        "pencil-wash",
        "red",
        "ok",
        "warn",
      ].map((key) => [key, style.getPropertyValue(`--${key}`).trim()]),
    );
  });
}

export async function verifyThemes(page, base) {
  const results = [];
  await page.goto(`${base.origin}/#/workbench`);
  await page.locator(".workbench-section").first().waitFor();
  for (const theme of ["light", "dark"]) {
    await appearance(page, "en", theme);
    await page.emulateMedia({
      colorScheme: theme === "light" ? "dark" : "light",
    });
    const explicit = await palette(page);
    await page.reload();
    await settle(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), theme);
    assert.equal(
      await page
        .getByRole("combobox", { name: "Theme", exact: true })
        .inputValue(),
      theme,
    );
    assert.deepEqual(
      await palette(page),
      explicit,
      "Explicit theme survives reload and overrides opposite media",
    );
    await page
      .getByRole("combobox", { name: "Theme", exact: true })
      .selectOption("system");
    await page.emulateMedia({ colorScheme: theme });
    await settle(page);
    assert.equal(await page.locator("html").getAttribute("data-theme"), null);
    const system = await palette(page);
    assert.deepEqual(
      system,
      explicit,
      "System media resolves to the same ten palette values",
    );
    results.push({
      theme,
      persistedAttribute: theme,
      systemAttribute: null,
      explicit,
      system,
    });
  }
  return results;
}

export async function preparePage(page, entry, fixture) {
  if (entry.name === "agent-advanced") {
    await page.locator(".delegation-step > summary").first().click();
    await page
      .locator(`[data-used-memory-id="${fixture.advanced.memoryId}"]`)
      .waitFor();
  } else if (entry.name === "evidence") {
    await page
      .locator(".dataset-selector select")
      .selectOption(fixture.datasetId);
    await page.locator(".evidence-sample-row").first().waitFor();
  } else if (entry.name === "catalog") {
    await page
      .locator(".catalog-source-tree > .catalog-list button")
      .filter({ has: page.getByText("ecommerce", { exact: true }) })
      .click();
    await page
      .locator(".catalog-nested-tables button")
      .filter({ has: page.getByText("ecommerce/main/orders", { exact: true }) })
      .click();
    await page.locator(".catalog-detail tbody tr").first().waitFor();
  } else if (entry.name === "ask") {
    await page.locator("#ask-question").fill(primaryQuestion);
    const response = page.waitForResponse(
      (item) =>
        new URL(item.url()).pathname === "/api/ask" &&
        item.request().method() === "POST",
    );
    await page.locator(".ask-composer button[type=submit]").click();
    const received = await response;
    assert.equal(received.status(), 200);
    const answer = await received.json();
    assert.equal(answer.status, "answered");
    assert.equal(answer.result.rows[0][0], 4979475);
    await page.locator(".answer-number").waitFor();
    return answer;
  } else if (entry.name === "approval") {
    await page
      .locator(`.approval-sheet[data-plan-id="${fixture.planId}"]`)
      .waitFor();
  }
  return null;
}
