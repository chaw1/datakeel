// Exercise generated local Ask results, SVG data, and independent persisted threads.
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

import { chromium } from "playwright";

import { appearance, localBase } from "./screenshots-helpers.mjs";

const base = localBase(process.argv[2] ?? "http://127.0.0.1:8828");
assert.ok(process.argv[3], "Pass an evidence directory outside the checkout");
const output = path.resolve(process.argv[3]);
await mkdir(output, { recursive: true });
const report = { checks: [], screenshots: [], errors: [], answers: [] };
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  timezoneId: "Asia/Shanghai",
  reducedMotion: "reduce",
  serviceWorkers: "block",
});
context.setDefaultTimeout(20_000);
await context.route("**/*", async (route) => {
  assert.equal(new URL(route.request().url()).origin, base.origin);
  await route.continue();
});
context.on("page", (page) => {
  page.on("pageerror", (error) => report.errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") report.errors.push(message.text());
  });
});
const page = await context.newPage();

async function ask(target, question) {
  await target.locator("#ask-question").fill(question);
  const pending = target.waitForResponse(
    (response) =>
      response.url() === new URL("/api/ask", base).href &&
      response.request().method() === "POST",
  );
  await target
    .locator(".ask-composer")
    .getByRole("button", { name: "Ask data", exact: true })
    .click();
  const response = await pending;
  assert.equal(response.status(), 200, await response.text());
  const answer = await response.json();
  assert.equal(answer.status, "answered", answer.message);
  assert.ok(answer.interpreted_question);
  await target.locator(".ask-understood").waitFor();
  assert.ok(
    (await target.locator(".ask-understood").textContent()).includes(
      answer.interpreted_question,
    ),
  );
  report.answers.push(answer);
  return answer;
}

async function screenshot(name) {
  await page.locator(".ask-chart").scrollIntoViewIfNeeded();
  const filename = `${name}.png`;
  await page.screenshot({ path: path.join(output, filename), fullPage: true });
  report.screenshots.push(filename);
}

async function themes(name) {
  for (const theme of ["light", "dark"]) {
    await appearance(page, "en", theme);
    await screenshot(`${name}-${theme}`);
  }
}

async function verifySvg(answer) {
  const svg = page.locator(".ask-chart svg");
  await svg.waitFor();
  assert.ok(await svg.getAttribute("aria-labelledby"));
  assert.ok(await svg.getAttribute("aria-describedby"));
  assert.ok(await svg.locator(":scope > title").textContent());
  assert.ok(await svg.locator(":scope > desc").textContent());
  const y = answer.result.columns.indexOf(answer.chart.y[0]);
  assert.deepEqual(
    await svg.locator("g[data-value]").evaluateAll((items) =>
      items.map((item) => ({
        row: Number(item.dataset.row),
        value: Number(item.dataset.value),
      })),
    ),
    answer.result.rows.flatMap((row, index) =>
      typeof row[y] === "number" ? [{ row: index, value: row[y] }] : [],
    ),
  );
  const styles = await svg
    .locator("text")
    .evaluateAll((items) =>
      items.map((item) => globalThis.getComputedStyle(item).fontSize),
    );
  assert.ok(styles.every((size) => Number.parseFloat(size) >= 12));
}

try {
  await page.goto(new URL("/#/ask", base).href);
  await appearance(page, "en", "light");
  const scalar = await ask(page, "上个季度华东区零售额是多少");
  assert.equal(scalar.chart.type, "scalar");
  await themes("scalar");
  report.checks.push(
    "Scalar card uses metric units and an accessible description",
  );

  const bar = await ask(page, "上个季度按零售区域零售额");
  assert.equal(bar.chart.type, "bar");
  await verifySvg(bar);
  await themes("bars");
  assert.equal(
    await page
      .getByRole("button", { name: "Horizontal bars", exact: true })
      .count(),
    0,
  );
  const tableButton = page.getByRole("button", { name: "Table", exact: true });
  await tableButton.focus();
  await tableButton.press("Enter");
  assert.equal(await tableButton.getAttribute("aria-pressed"), "true");
  assert.equal(
    await page.locator(".ask-chart tbody tr").count(),
    bar.result.rows.length,
  );
  await screenshot("keyboard-table");
  const automaticButton = page.getByRole("button", {
    name: "Columns",
    exact: true,
  });
  await automaticButton.focus();
  await automaticButton.press("Enter");
  await verifySvg(bar);
  report.checks.push(
    "Automatic bar SVG values equal authoritative rows; keyboard table and return to automatic chart",
  );

  const ungrouped = await ask(page, "上个季度零售额");
  const line = await ask(page, "按月拆开");
  assert.equal(line.conversation_id, ungrouped.conversation_id);
  assert.equal(line.chart.type, "line");
  await verifySvg(line);
  await themes("line");
  report.checks.push(
    "Follow-up creates a monthly time series through the same metric engine",
  );

  const grouped = await ask(page, "上个季度按零售区域按零售渠道零售额");
  assert.equal(grouped.chart.type, "grouped_bar");
  await verifySvg(grouped);
  await themes("grouped");
  assert.equal(
    await page
      .getByRole("button", { name: "Stacked columns", exact: true })
      .count(),
    0,
  );
  report.checks.push(
    "Two dimensions render automatic grouped bars without changing values",
  );

  const daily = await ask(page, "上个季度按日零售额");
  assert.ok(daily.result.rows.length > 30);
  assert.equal(daily.chart.type, "table");
  assert.equal(await page.locator(".ask-chart svg").count(), 0);
  await screenshot("table-only");

  await ask(page, "上个季度华东零售额");
  const compared = await ask(page, "同比");
  assert.ok(compared.comparison);
  await page.locator(".ask-comparison").waitFor();
  await themes("comparison");
  const identity = compared.conversation_id;
  await page.reload();
  await page.locator(".ask-understood").waitFor();
  assert.equal(
    await page.evaluate(() =>
      globalThis.sessionStorage.getItem("datakeel.ask.conversation"),
    ),
    identity,
  );
  assert.ok(
    (await page.locator(".ask-understood").textContent()).includes(
      compared.interpreted_question,
    ),
  );
  report.checks.push(
    "Reload restores the persisted conversation and comparison",
  );

  const other = await context.newPage();
  await other.goto(new URL("/#/ask", base).href);
  const independent = await ask(other, "上个月订单数");
  assert.notEqual(independent.conversation_id, identity);
  await page.reload();
  await page.locator(".ask-understood").waitFor();
  assert.equal(
    await page.evaluate(() =>
      globalThis.sessionStorage.getItem("datakeel.ask.conversation"),
    ),
    identity,
  );
  report.checks.push("Two tabs keep independent conversation identifiers");
  await other.close();

  await page
    .getByRole("button", { name: "Saved conversations", exact: true })
    .click();
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  assert.equal(await page.locator(".ask-understood").count(), 0);
  const thread = page.locator(`li[data-conversation-id="${identity}"]`);
  assert.equal(await thread.count(), 1);
  await thread
    .getByRole("button", {
      name: "Open conversation: 上个季度华东区零售额是多少",
      exact: true,
    })
    .click();
  await page.locator(".ask-understood").waitFor();
  const deletion = page.waitForResponse(
    (response) =>
      response.request().method() === "DELETE" &&
      response.url().endsWith(identity),
  );
  await thread
    .getByRole("button", {
      name: "Delete conversation: 上个季度华东区零售额是多少",
      exact: true,
    })
    .click();
  assert.equal((await deletion).status(), 204);
  assert.equal(await page.locator(".ask-understood").count(), 0);
  const deleted = await context.request.get(
    new URL(`/api/ask/conversations/${identity}`, base).href,
  );
  assert.equal(deleted.status(), 404);
  report.checks.push(
    "List, open, and delete operate on persisted threads; deleted thread returns 404",
  );
  assert.deepEqual(report.errors, []);
} finally {
  await writeFile(
    path.join(output, "report.json"),
    `${JSON.stringify(report, null, 2)}\n`,
  );
  await browser.close();
}
process.stdout.write(
  JSON.stringify({
    checks: report.checks,
    screenshots: report.screenshots,
    errors: report.errors,
  }),
);
