import assert from "node:assert/strict";

const selector =
  "h1, h2, .stat-number, .answer-number, .page-title, table td, .nav a, button, p";

export async function typographySample(page, name) {
  await page.evaluate(() => globalThis.document.fonts.ready);
  const samples = await page.locator(selector).evaluateAll((elements) =>
    elements
      .filter((element) => element.getClientRects().length)
      .map((element) => {
        const style = globalThis.getComputedStyle(element);
        return {
          tag: element.tagName,
          className: element.className,
          text: element.textContent.trim().slice(0, 60),
          size: parseFloat(style.fontSize),
          family: style.fontFamily.split(",")[0].replaceAll('"', "").trim(),
          weight: style.fontWeight,
        };
      }),
  );
  assert.ok(samples.length > 0, `${name}: typography samples exist`);
  for (const sample of samples) {
    assert.equal(
      sample.family === "Source Serif 4",
      sample.size >= 18,
      `${name}: ${JSON.stringify(sample)}`,
    );
    if (sample.size < 18)
      assert.ok(["-apple-system", "Source Code Pro"].includes(sample.family));
  }
  return { name, samples };
}

export async function mobileWidth(page, name) {
  const measure = await page.evaluate(() => ({
    viewport: globalThis.window.innerWidth,
    width: globalThis.document.documentElement.scrollWidth,
    overflow: Array.from(globalThis.document.querySelectorAll("main *"))
      .filter((element) => {
        const rect = element.getBoundingClientRect();
        return rect.width && rect.right > globalThis.window.innerWidth + 1;
      })
      .slice(0, 12)
      .map((element) => `${element.tagName}.${element.className}`),
  }));
  assert.ok(
    measure.width <= measure.viewport + 1,
    `${name}: horizontal page overflow ${JSON.stringify(measure)}`,
  );
  return { name, ...measure };
}

export async function polishSmoke({ page, json, screenshot, checks }) {
  const origin = new URL(page.url()).origin;
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page.setViewportSize({ width: 1440, height: 900 });
  const objects = await json("/api/search?limit=100");
  const kinds = [
    "dataset",
    "file",
    "version",
    "action_run",
    "table",
    "column",
    "metric",
    "term",
  ];
  const writes = [];
  const observe = (request) => {
    if (
      !["GET", "HEAD"].includes(request.method()) &&
      new URL(request.url()).pathname !== "/api/evidence/query"
    )
      writes.push(request.url());
  };
  page.on("request", observe);
  const input = page.getByRole("combobox", { name: "Object name or ID" });
  for (const kind of kinds) {
    const object = objects.find((item) => item.kind === kind);
    assert.ok(object, kind);
    await page.keyboard.press("Control+k");
    await input.fill(object.id);
    await page
      .getByRole("option")
      .filter({ hasText: object.name })
      .first()
      .waitFor();
    await input.press("Enter");
    await page.waitForURL((url) =>
      url.hash.startsWith(`#/object/${kind}/${encodeURIComponent(object.id)}?`),
    );
    await page.locator(".object-header h1").waitFor();
  }
  const dataset = objects.find((item) => item.kind === "dataset");
  for (const text of [dataset.id, dataset.id.slice(0, 8)]) {
    await page.keyboard.press("Meta+k");
    await input.waitFor();
    await input.evaluate((element, value) => {
      const clipboardData = new globalThis.DataTransfer();
      clipboardData.setData("text", value);
      element.dispatchEvent(
        new globalThis.ClipboardEvent("paste", {
          clipboardData,
          bubbles: true,
          cancelable: true,
        }),
      );
    }, text);
    await page.waitForURL((url) =>
      url.hash.startsWith(`#/object/dataset/${dataset.id}?`),
    );
    await page.getByRole("dialog").waitFor({ state: "detached" });
  }
  await page.keyboard.press("Control+k");
  await input.fill(dataset.id);
  await page.getByRole("option").filter({ hasText: dataset.name }).waitFor();
  await screenshot("command-palette", false);
  const typography = [await typographySample(page, "command-palette")];
  await page
    .getByRole("button", {
      name: `Start a conversation about ${dataset.name}`,
      exact: true,
    })
    .click();
  await page.waitForURL(/#\/agent\?prompt=/);
  const draft = page.getByRole("textbox", { name: "Message", exact: true });
  await draft.waitFor();
  assert.ok((await draft.inputValue()).includes(dataset.name));
  assert.ok((await draft.inputValue()).includes(dataset.id));
  assert.deepEqual(
    writes,
    [],
    "Search, paste and conversation draft never execute an action",
  );
  page.off("request", observe);
  checks.push(
    "command palette opens all eight object kinds, unique full UUID and eight-character paste navigate, and a conversation draft never sends or executes",
  );

  const table = objects.find((item) => item.kind === "table");
  const routes = [
    ["workbench", "#/workbench", ".workbench-section"],
    ["evidence", "#/evidence", ".evidence-sample-row"],
    ["ask", "#/ask", ".ask-composer"],
    ["catalog", "#/catalog", ".catalog-browser"],
    [
      "table",
      `#/object/table/${encodeURIComponent(table.id)}?tab=relations`,
      ".object-body",
    ],
    ["metric", "#/object/metric/retail_revenue?tab=relations", ".object-body"],
    ["approvals", "#/approvals", ".approval-sheet"],
    ["runs", "#/runs", "main table"],
    ["agent", "#/agent", ".message-composer"],
  ];
  const mobile = [];
  for (const [name, hash, ready] of routes) {
    await page.goto(`${origin}/${hash}`);
    await page.locator(ready).first().waitFor();
    if (name === "ask") {
      await page
        .getByRole("button", {
          name: "East China retail revenue · last quarter",
          exact: true,
        })
        .click();
      await page
        .locator(".ask-composer")
        .getByRole("button", { name: "Ask data", exact: true })
        .click();
      await page.locator(".answer-number").waitFor();
    }
    typography.push(await typographySample(page, name));
    await page.setViewportSize({ width: 390, height: 844 });
    await page.evaluate(async () => {
      globalThis.scrollTo(0, 0);
      await new Promise((resolve) => globalThis.requestAnimationFrame(resolve));
      await new Promise((resolve) => globalThis.requestAnimationFrame(resolve));
    });
    mobile.push(await mobileWidth(page, name));
    await screenshot(`mobile-${name}`, false);
    await page.setViewportSize({ width: 1440, height: 900 });
  }
  checks.push(
    "computed fonts obey the 18px serif boundary across all major pages; all nine layouts fit 390px without horizontal page scrolling",
  );
  return { typography, mobile };
}
