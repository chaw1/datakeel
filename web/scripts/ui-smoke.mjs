// Run only against an isolated `datakeel demo` fixture; this test changes its data.
// npm run smoke:ui -- http://127.0.0.1:8773 [output-directory]
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { advancedSmoke } from "./advanced-smoke.mjs";
import { enterpriseSmoke } from "./enterprise-smoke.mjs";
import { evidenceSmoke } from "./evidence-smoke.mjs";
import { extractionSmoke } from "./extraction-smoke.mjs";
import { polishSmoke } from "./polish-smoke.mjs";
import { refinementSmoke } from "./refinement-smoke.mjs";
import { workspaceSmoke } from "./workspace-smoke.mjs";
import {
  cleanupFixture,
  workflowJourney,
  workflowRoutingSmoke,
} from "./workflow-smoke.mjs";

const { version } = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const base = new URL(process.argv[2] ?? "http://127.0.0.1:8773");
assert.equal(base.protocol, "http:", "Use the local HTTP demo");
assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
const output = path.resolve(
  process.argv[3] ??
    fileURLToPath(new URL("../../artifacts/ui-smoke", import.meta.url)),
);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  timezoneId: "Asia/Shanghai",
});
context.setDefaultTimeout(30_000);
const errors = [];
const checks = [];
const page = await context.newPage();
page.on("pageerror", (error) => errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});
await context.route("**/*", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  assert.equal(
    url.origin,
    base.origin,
    "The smoke must never contact external services",
  );
  if (
    url.pathname === "/api/agent/conversations" &&
    request.method() === "POST"
  )
    assert.equal(request.postDataJSON().provider, "fake");
  await route.continue();
});
async function json(endpoint) {
  const response = await context.request.get(new URL(endpoint, base).href);
  assert.equal(response.ok(), true, endpoint);
  return response.json();
}
async function post(endpoint, data) {
  const response = await context.request.post(new URL(endpoint, base).href, {
    data,
  });
  assert.equal(response.ok(), true, endpoint);
  return response.json();
}
async function send(message) {
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill(message);
  const terminal = page.waitForResponse(
    (response) =>
      response.url().endsWith("/messages") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const response = await terminal;
  assert.equal(response.status(), 200);
  const stream = await response.text();
  assert.match(stream, /event: done/);
  await page.getByRole("textbox", { name: "Message", exact: true }).waitFor();
  await page.locator(".message-composer textarea:enabled").waitFor();
  return stream;
}
async function screenshot(name, fullPage = true) {
  assert.doesNotMatch(await page.locator("body").innerText(), /\bP[56]\b/);
  await page.screenshot({
    path: path.join(output, `${name}.png`),
    fullPage,
  });
}
async function waitForDemo() {
  const deadline = Date.now() + 120_000;
  while (Date.now() < deadline) {
    const tasks = await json("/api/tasks");
    assert.ok(
      !tasks.some((task) => task.state === "FAILED"),
      "Demo task failed",
    );
    if (tasks.length >= 2 && tasks.every((task) => task.state === "COMPLETED"))
      return;
    await delay(500);
  }
  throw new Error("Waited for the isolated demo extraction to finish");
}
try {
  await waitForDemo();
  await page.goto(base.href);
  await page.getByText(`v${version}`, { exact: true }).waitFor();
  assert.equal((await json("/api/openapi.json")).info.version, version);
  const favicon = await context.request.get(new URL("/favicon.svg", base).href);
  assert.equal(favicon.status(), 200);
  const icon = await favicon.text();
  assert.match(icon, /fill="#F7F5EE"/);
  assert.match(icon, /fill="#2459A8"/);
  assert.match(icon, /rotate\(-13 13 14\.5\)/);
  assert.doesNotMatch(icon, /#35795d|#edf4ef/i);
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("en");
  const theme = page.getByRole("combobox", { name: "Theme", exact: true });
  await theme.selectOption("dark");
  assert.equal(await page.locator("html").getAttribute("data-theme"), "dark");
  const explicitDarkPaper = await page
    .locator("html")
    .evaluate((element) =>
      globalThis.getComputedStyle(element).getPropertyValue("--paper").trim(),
    );
  await page.reload();
  assert.equal(await theme.inputValue(), "dark");
  await theme.selectOption("system");
  await page.emulateMedia({ colorScheme: "dark" });
  assert.equal(await page.locator("html").getAttribute("data-theme"), null);
  const darkPaper = await page
    .locator("html")
    .evaluate((element) =>
      globalThis.getComputedStyle(element).getPropertyValue("--paper").trim(),
    );
  assert.equal(darkPaper, explicitDarkPaper);
  await theme.selectOption("light");
  await page.emulateMedia({ colorScheme: "light" });
  assert.equal(
    await page
      .locator(".brand-mark span")
      .first()
      .evaluate(
        (element) => globalThis.getComputedStyle(element).backgroundColor,
      ),
    "rgb(36, 89, 168)",
  );
  const logoGeometry = await page.evaluate((svg) => {
    const mark = globalThis.document.querySelector(".brand-mark");
    const style = globalThis.getComputedStyle(mark);
    const spans = Array.from(mark.children).map((element, index) => {
      const bar = globalThis.getComputedStyle(element);
      const width = parseFloat(bar.width);
      const height = parseFloat(bar.height);
      const available = parseFloat(style.height) - height;
      return [
        index * (width + parseFloat(style.gap)),
        bar.alignSelf === "flex-end"
          ? available
          : bar.alignSelf === "flex-start"
            ? 0
            : available / 2,
        width,
        height,
        parseFloat(bar.borderRadius),
      ];
    });
    const document = new globalThis.DOMParser().parseFromString(
      svg,
      "image/svg+xml",
    );
    const bars = Array.from(document.querySelectorAll("g rect")).map((bar) =>
      ["x", "y", "width", "height", "rx"].map((attribute) =>
        Number(bar.getAttribute(attribute)),
      ),
    );
    return { spans, bars };
  }, icon);
  assert.deepEqual(logoGeometry.bars, logoGeometry.spans);
  checks.push(
    "package/API/sidebar versions agree; favicon matches the blue logo and paper palette",
  );
  checks.push(
    "explicit and system themes switch; explicit choice survives reload",
  );
  assert.equal(await page.locator("[data-nav-group]").count(), 6);
  await page.getByRole("link", { name: "Data library", exact: true }).click();
  const datasets = await json("/api/datasets");
  const legacy = datasets.find((dataset) => !dataset.metadata.evidence_samples);
  assert.ok(legacy, "Keep the P1/P2 regression on its original fixture");
  await page
    .locator(".dataset-card")
    .filter({
      has: page.getByRole("heading", { name: legacy.name, exact: true }),
    })
    .click();
  await page.getByRole("heading", { name: legacy.name, exact: true }).waitFor();
  const versions = await json(`/api/datasets/${legacy.id}/versions`);
  assert.equal(versions.length, 2);
  assert.equal(
    await page.locator('[data-fact="objCurrentVersion"] strong').textContent(),
    "2",
  );
  assert.match(
    await page.locator('[data-fact="objQuality"] strong').textContent(),
    /^\d/,
  );
  const initialTasks = await json("/api/tasks");
  assert.equal(
    initialTasks.filter((task) => task.dataset_id === legacy.id).length,
    1,
  );
  await screenshot("legacy-dataset");
  await page
    .locator(".object-tabs")
    .getByRole("link", { name: "Quality", exact: true })
    .click();
  await page.waitForURL(/tab=quality/);
  await page.locator(".dimension-list .dimension").first().waitFor();
  await screenshot("legacy-quality");
  await page
    .locator(".object-tabs")
    .getByRole("link", { name: "Report", exact: true })
    .click();
  await page.waitForURL(/tab=report/);
  await page.locator(".report-chapter").first().waitFor();
  assert.ok((await page.locator(".report-chapter").count()) > 0);
  await screenshot("legacy-report");
  checks.push(
    "original dataset, five-dimension quality and baseline report pages still render real data",
  );
  await page.getByRole("link", { name: "Agent", exact: true }).click();
  await page
    .getByRole("combobox", {
      name: "Dataset for a new conversation",
      exact: true,
    })
    .selectOption(legacy.id);
  await page.getByText("Conversation budget", { exact: true }).first().click();
  await page
    .getByRole("spinbutton", { name: "Conversation token limit", exact: true })
    .fill("1000000");
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/agent/conversations") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  const conversation = await (await created).json();
  assert.equal(conversation.config.provider, "fake");
  const search = await send("Find text files with quality below 60");
  assert.match(search, /search_files/);
  await page.getByText("Tool call", { exact: false }).first().click();
  assert.equal(
    await page.getByText("Arguments", { exact: true }).first().isVisible(),
    true,
  );
  checks.push("real POST SSE search and folded tool arguments");
  const quarantine = await send("Quarantine those files and create a version");
  assert.match(quarantine, /event: receipt/);
  assert.match(quarantine, /create_version_from_selection/);
  assert.equal(
    await page
      .getByRole("button", { name: "Approve and delete files" })
      .count(),
    0,
  );
  const saved = await json(`/api/agent/conversations/${conversation.id}`);
  const automatic = saved.events.filter((event) => event.event === "receipt");
  assert.ok(automatic.length >= 2);
  assert.ok(
    automatic.every((event) => event.outcome.run.status === "SUCCEEDED"),
  );
  const runsBeforeDelete = await json("/api/actions/runs");
  checks.push("multi-turn memory, automatic quarantine and version receipts");
  const approvalsBefore = (await json("/api/approvals")).length;
  const deletion = await send("Delete those files");
  await page
    .locator(`[data-pending-count="${approvalsBefore + 1}"]`)
    .waitFor({ timeout: 2000 });
  assert.match(deletion, /approval_required/);
  assert.equal(
    (await json("/api/actions/runs")).length,
    runsBeforeDelete.length,
  );
  assert.equal(
    await page
      .getByText("Stopped: approval_required.", { exact: true })
      .count(),
    0,
  );
  await screenshot("agent-pending-delete");
  await page.getByRole("button", { name: "Return", exact: true }).click();
  await page
    .getByRole("button", { name: "Return", exact: true })
    .waitFor({ state: "detached" });
  assert.equal(
    (await json("/api/actions/runs")).length,
    runsBeforeDelete.length,
  );
  await page
    .locator(`[data-pending-count="${approvalsBefore}"]`)
    .waitFor({ timeout: 2000 });
  checks.push(
    "irreversible action waits; rejecting causes no execution and immediately refreshes the approval count",
  );
  await send("Delete those files");
  const executed = page.waitForResponse(
    (response) =>
      response.url().endsWith("/execute") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Approve and delete files", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Approve and delete files", exact: true })
    .waitFor({ state: "detached" });
  assert.equal((await executed).status(), 200);
  await page
    .locator(`[data-pending-count="${approvalsBefore}"]`)
    .waitFor({ timeout: 2000 });
  const runs = await json("/api/actions/runs");
  const deletionRun = runs.find(
    (run) =>
      run.action_type === "delete_files" &&
      !runsBeforeDelete.some((old) => old.id === run.id),
  );
  assert.equal(deletionRun?.status, "SUCCEEDED");
  await page
    .locator(`a[href*="event=${deletionRun.receipt.event_id}"]`)
    .waitFor();
  await screenshot("agent-executed");
  await page
    .getByRole("link", { name: "View lineage receipt", exact: true })
    .last()
    .click();
  await page.getByRole("link", { name: "Agent", exact: true }).waitFor();
  await page.waitForURL(/#\/object\/.+tab=relations/);
  await screenshot("receipt-lineage");
  checks.push(
    "explicit approval executes once and receipt navigates to lineage",
  );
  await page.getByRole("link", { name: "Agent", exact: true }).click();
  await page
    .getByRole("button", { name: "View trace & costs", exact: true })
    .click();
  await page.getByRole("heading", { name: /^Trace & costs ·/ }).waitFor();
  await page
    .getByRole("region", { name: "Input token segments" })
    .first()
    .waitFor();
  const traces = await json(
    `/api/harness/traces?conversation_id=${conversation.id}`,
  );
  assert.ok(traces.length > 0);
  for (const group of ["conversation", "day", "model"]) {
    await page
      .getByRole("combobox", { name: "Group costs by" })
      .selectOption(group);
    const costs = await json(`/api/harness/costs?group_by=${group}`);
    assert.ok(costs.length > 0);
    assert.ok(costs.every((cost) => cost.group_by === group));
  }
  await screenshot("trace-costs");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await page.getByRole("heading", { name: /^调用追踪与成本 ·/ }).waitFor();
  await screenshot("trace-zh");
  checks.push("real token bars, cache, latency, three cost summaries, zh/en");
  await page.getByRole("link", { name: "审批待办", exact: true }).click();
  await page.getByRole("heading", { name: /^审批待办 ·/ }).waitFor();
  await screenshot("approvals-zh");
  await page.getByRole("link", { name: "本体浏览", exact: true }).click();
  await page.getByRole("heading", { name: /^本体浏览 ·/ }).waitFor();
  await page.getByRole("heading", { name: "dataset", exact: true }).waitFor();
  await screenshot("ontology-zh");
  checks.push("approval queue and ontology render with Chinese labels");
  const evidence = await evidenceSmoke({
    page,
    json,
    post,
    screenshot,
    checks,
  });
  const enterprise = await enterpriseSmoke({
    page,
    json,
    post,
    screenshot,
    checks,
  });
  const workspace = await workspaceSmoke({
    page,
    json,
    post,
    screenshot,
    checks,
  });
  const polish = await polishSmoke({ page, json, screenshot, checks });
  const refinement = await refinementSmoke({ page, json, screenshot, checks });
  const extraction = process.argv[5]
    ? await extractionSmoke({
        page,
        json,
        datasetId: process.argv[5],
        viaObject: process.argv[6] === "object",
        screenshot,
        checks,
      })
    : null;
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/, exact: true })
    .selectOption("en");
  const workflows = await workflowJourney({
    page,
    base,
    dataset: await cleanupFixture(post),
    json,
  });
  await screenshot("workflows-complete");
  const routing = await workflowRoutingSmoke({
    page,
    base,
    datasetId: workflows.datasetId,
    json,
  });
  await screenshot("workflow-route-prefill");
  checks.push(
    "workflow schema form, isolated cleanup, approval link, explicit resume, persisted timeline and exactly one deletion",
  );
  const advanced = await advancedSmoke({
    page,
    base,
    json,
    post,
    send,
    screenshot,
    checks,
    datasetId: workflows.datasetId,
  });
  assert.deepEqual(errors, []);
  await writeFile(
    path.join(output, "evidence.json"),
    JSON.stringify(
      {
        phase: process.argv[4] ?? "P2 smoke",
        frontendVersion: version,
        base: base.href,
        conversationId: conversation.id,
        deletionRunId: deletionRun.id,
        traces: traces.length,
        evidence,
        enterprise,
        workspace,
        polish,
        refinement,
        extraction,
        workflows,
        routing,
        advanced,
        checks,
        errors,
      },
      null,
      2,
    ),
  );
  process.stdout.write(
    `${JSON.stringify({ output, checks, errors }, null, 2)}\n`,
  );
} catch (error) {
  process.stderr.write(`${error.stack}\n`);
  await screenshot("failure", false);
  throw error;
} finally {
  await writeFile(
    path.join(output, "console.json"),
    JSON.stringify(errors, null, 2),
  );
  await browser.close();
}
