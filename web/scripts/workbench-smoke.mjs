// Run against generated personal fixtures, using the app's real local API only.
// npm run smoke:workbench -- http://127.0.0.1:8840 OUTPUT MANIFEST [--only=W1,W2]
import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "playwright";

import { createHarness, workbenchBase } from "./workbench-helpers.mjs";
import { keyboardWorkflow, unlimitedHistory } from "./workbench-keyboard.mjs";
import { largeImages, nextTaskLatency } from "./workbench-performance.mjs";
import { durableEditing } from "./workbench-reliability.mjs";

const base = workbenchBase(process.argv[2] ?? "http://127.0.0.1:8840");
assert.ok(
  process.argv[3] && process.argv[4],
  "Pass an output directory and generated fixture manifest",
);
const output = path.resolve(process.argv[3]);
const manifest = JSON.parse(
  await readFile(path.resolve(process.argv[4]), "utf8"),
);
assert.equal(manifest.actor, "local", "Use generated local personal fixtures");
for (const kind of [
  "box",
  "polygon",
  "classification",
  "text_span",
  "large4k",
  "large8k",
]) {
  assert.match(manifest.projects[kind].project_id, /^[a-zA-Z0-9-]+$/);
  assert.ok(
    manifest.projects[kind].task_ids.every((id) => /^[a-zA-Z0-9-]+$/.test(id)),
  );
}
const selected = (
  process.argv.find((item) => item.startsWith("--only="))?.slice(7) ??
  "W1,W2,W3,W4,W5"
).split(",");
assert.ok(selected.every((name) => /^W[1-5]$/.test(name)));
await mkdir(output, { recursive: true });
const report = {
  startedAt: new Date().toISOString(),
  base: base.origin,
  selected,
  status: "running",
  checks: {},
  errors: [],
  expectedNetworkErrors: [],
  blockedRequests: [],
  expectedFailurePhase: null,
};
let browser;
let page;
try {
  // One launch attempt. A sandbox failure is recorded without a launch workaround.
  browser = await chromium.launch({
    headless: true,
    ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    timezoneId: "Asia/Shanghai",
    serviceWorkers: "block",
    extraHTTPHeaders: { "X-Datakeel-Actor": manifest.actor },
  });
  context.setDefaultTimeout(20_000);
  await context.addInitScript(() => {
    globalThis.localStorage.setItem("datakeel.locale", "en");
    globalThis.localStorage.setItem("datakeel.theme", "light");
  });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== base.origin) {
      report.blockedRequests.push(url.href);
      await route.abort("blockedbyclient");
    } else await route.continue();
  });
  page = await context.newPage();
  page.on("pageerror", (error) =>
    report.errors.push({
      phase: report.phase,
      kind: "pageerror",
      message: error.message,
    }),
  );
  page.on("console", (entry) => {
    if (entry.type() !== "error") return;
    const message = entry.text();
    const expected =
      report.expectedFailurePhase &&
      /Failed to load resource.*(?:ERR_INTERNET_DISCONNECTED|ERR_FAILED|409|503)/.test(
        message,
      );
    (expected ? report.expectedNetworkErrors : report.errors).push({
      phase: report.expectedFailurePhase ?? report.phase,
      kind: "console",
      message,
    });
  });
  const h = createHarness(context, page, base, output, manifest, report);
  for (const [name, run] of [
    ["W1", nextTaskLatency],
    ["W2", keyboardWorkflow],
    ["W3", durableEditing],
    ["W4", unlimitedHistory],
    ["W5", largeImages],
  ]) {
    if (!selected.includes(name)) continue;
    report.phase = name;
    process.stdout.write(`${name} started\n`);
    report.checks[name] = await run(h);
    process.stdout.write(`${name} passed\n`);
  }
  report.phase = "screenshots";
  for (const locale of ["en", "zh"])
    for (const theme of ["light", "dark"]) {
      await page
        .getByRole("combobox", { name: /^(Language|语言)$/ })
        .selectOption(locale);
      await page
        .getByRole("combobox", { name: /^(Theme|主题)$/ })
        .selectOption(theme);
      await h.capture(`workbench-${locale}-${theme}`);
      assert.equal(await page.locator("html").getAttribute("lang"), locale);
      assert.equal(
        await page.locator("html").getAttribute("data-theme"),
        theme,
      );
    }
  assert.deepEqual(report.errors, [], "No unexpected browser errors");
  assert.deepEqual(report.blockedRequests, [], "No external requests");
  report.status = "passed";
} catch (reason) {
  report.status = browser ? "failed" : "blocked";
  report.failure = reason instanceof Error ? reason.stack : String(reason);
  if (page)
    await page
      .screenshot({
        path: path.join(output, "workbench-failure.png"),
        fullPage: true,
      })
      .catch(() => undefined);
  process.stderr.write(`${report.failure}\n`);
  process.exitCode = browser ? 1 : 2;
} finally {
  report.finishedAt = new Date().toISOString();
  await writeFile(
    path.join(output, "workbench-ui-smoke.json"),
    `${JSON.stringify(report, null, 2)}\n`,
  );
  await browser?.close();
}
