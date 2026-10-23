// Capture only the generated loopback demo. A missing approval is prepared, never executed.
// npm run screenshots -- http://127.0.0.1:8773 [output-directory]
import assert from "node:assert/strict";
import { mkdir, readdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { typographySample } from "./polish-smoke.mjs";
import {
  appearance,
  fixedTime,
  localApi,
  localBase,
  pages,
  prepareFixture,
  preparePage,
  settle,
  variants,
  verifyThemes,
  viewport,
} from "./screenshots-helpers.mjs";

const base = localBase(process.argv[2] ?? "http://127.0.0.1:8773");
const { version } = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const output = path.resolve(
  process.argv[3] ??
    fileURLToPath(new URL("../../artifacts/screenshots", import.meta.url)),
);
const expectedFiles = pages
  .flatMap(({ name }) =>
    variants.map(({ locale, theme }) => `${name}-${locale}-${theme}.png`),
  )
  .sort();
assert.equal(expectedFiles.length, 40);
await mkdir(output, { recursive: true });
const existing = (await readdir(output)).filter((name) =>
  name.endsWith(".png"),
);
assert.ok(
  existing.every((name) => expectedFiles.includes(name)),
  "Output contains unrelated PNGs; use a dedicated screenshot directory",
);
const report = {
  fixedTime,
  base: base.origin,
  viewport,
  timezone: "Asia/Shanghai",
  expectedFiles,
  fixture: null,
  themeChecks: [],
  pages: [],
  errors: [],
  blockedRequests: [],
  writes: [],
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
let currentName = "fixture";
let askPosts = 0;
let replayGets = 0;
context.on("page", (page) => {
  page.on("pageerror", (error) =>
    report.errors.push({
      page: currentName,
      kind: "pageerror",
      message: error.message,
    }),
  );
  page.on("console", (message) => {
    if (message.type() === "error")
      report.errors.push({
        page: currentName,
        kind: "console",
        message: message.text(),
      });
  });
});
await context.addInitScript(() => {
  if (globalThis.location.protocol !== "http:") return;
  if (!globalThis.localStorage.getItem("datakeel.locale"))
    globalThis.localStorage.setItem("datakeel.locale", "zh");
  if (!globalThis.localStorage.getItem("dk-theme"))
    globalThis.localStorage.setItem("dk-theme", "light");
});
await context.route("**/*", async (route) => {
  const request = route.request();
  const url = new URL(request.url());
  if (url.origin !== base.origin) {
    report.blockedRequests.push({ page: currentName, url: url.href });
    await route.abort("blockedbyclient");
    return;
  }
  if (!["GET", "HEAD"].includes(request.method())) {
    if (
      request.method() !== "POST" ||
      !["/api/ask", "/api/evidence/query"].includes(url.pathname)
    ) {
      report.errors.push({
        page: currentName,
        kind: "blocked-write",
        message: `${request.method()} ${url.pathname}`,
      });
      await route.abort("blockedbyclient");
      return;
    }
    if (url.pathname === "/api/ask") {
      askPosts += 1;
      report.writes.push({ method: "POST", url: url.href, phase: currentName });
      if (askPosts > 1) {
        report.errors.push({
          page: currentName,
          kind: "blocked-write",
          message: "Only one real Ask request is permitted per run",
        });
        await route.abort("blockedbyclient");
        return;
      }
    }
  } else if (url.pathname.startsWith("/api/ask/")) replayGets += 1;
  await route.continue();
});
const api = localApi(context, base, report.writes);
try {
  report.fixture = await prepareFixture(api);
  currentName = "theme-verification";
  const themePage = await context.newPage();
  await themePage.clock.setFixedTime(new Date(fixedTime));
  report.themeChecks = await verifyThemes(themePage, base);
  await themePage.close();
  const page = await context.newPage();
  await page.clock.setFixedTime(new Date(fixedTime));
  for (const entry of pages) {
    currentName = `${entry.name}-setup`;
    await page.goto(`${base.origin}/${entry.hash}`);
    await page.locator(entry.ready).first().waitFor();
    const answer = await preparePage(page, entry, report.fixture);
    for (const [index, { locale, theme }] of variants.entries()) {
      const name = `${entry.name}-${locale}-${theme}`;
      currentName = name;
      if (entry.name === "command-palette" && index > 0)
        await page.keyboard.press("Escape");
      await appearance(page, locale, theme);
      if (entry.name === "ask" && index > 0) {
        const replayed = page.waitForResponse(
          (response) =>
            new URL(response.url()).pathname === `/api/ask/${answer.id}` &&
            response.request().method() === "GET",
        );
        await page.locator(".ask-replay button").first().click();
        assert.deepEqual(await (await replayed).json(), answer);
        await page.locator(".answer-number").waitFor();
      }
      if (entry.name === "command-palette") {
        await page.keyboard.press("Control+k");
        await page.locator(".command-dialog [role=option]").first().waitFor();
      }
      await settle(page);
      const visibleText = await page.locator("body").innerText();
      assert.doesNotMatch(visibleText, /\bP[56]\b/);
      assert.ok(visibleText.includes(`v${version}`));
      assert.doesNotMatch(
        visibleText,
        locale === "en"
          ? /\b1 (?:items|objects)\b/
          : /\b(?:Pipeline run|COMPLETED|SUCCEEDED)\b/,
        `${name}: no known untranslated or pluralized UI remnants`,
      );
      await writeFile(path.join(output, `${name}.txt`), `${visibleText}\n`);
      const typography = await typographySample(page, name);
      const metadata = await page.evaluate(() => ({
        locale: globalThis.document.documentElement.lang,
        theme: globalThis.document.documentElement.dataset.theme,
        clock: new Date().toISOString(),
        width: globalThis.innerWidth,
        height: globalThis.innerHeight,
      }));
      assert.equal(metadata.clock, fixedTime.replace("Z", ".000Z"));
      assert.equal(metadata.locale, locale);
      assert.equal(metadata.theme, theme);
      const filename = `${name}.png`;
      const image = await page.screenshot({
        path: path.join(output, filename),
        fullPage: false,
        animations: "disabled",
      });
      if (entry.name === "evidence" && theme === "light")
        assert.ok(image.length <= 400_000, "README screenshot exceeds 400KB");
      report.pages.push({
        name,
        filename,
        bytes: image.length,
        route: entry.hash,
        ...metadata,
        typography: typography.samples,
        consoleErrors: report.errors.filter(
          (error) =>
            error.page === name || error.page === `${entry.name}-setup`,
        ),
      });
      process.stdout.write(`${filename}\n`);
    }
    if (entry.name === "command-palette") await page.keyboard.press("Escape");
  }
  const plan = await api.json(`/api/actions/plans/${report.fixture.planId}`);
  assert.equal(
    plan.status,
    "PREPARED",
    "Screenshots must leave approval unexecuted",
  );
  assert.equal(
    (await api.json(`/api/datasets/${report.fixture.datasetId}/files`)).length,
    report.fixture.fileCount,
  );
  assert.equal(askPosts, 1);
  assert.equal(replayGets, 3);
  report.askRequests = { posts: askPosts, replayGets };
  assert.deepEqual(report.blockedRequests, [], "No external-domain requests");
  assert.deepEqual(
    report.errors,
    [],
    "Every captured page must have zero console errors",
  );
  assert.equal(report.pages.length, 40);
  assert.deepEqual(
    (await readdir(output)).filter((name) => name.endsWith(".png")).sort(),
    expectedFiles,
  );
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.failure = {
    page: currentName,
    message: error instanceof Error ? error.stack : String(error),
  };
  process.exitCode = 1;
  process.stderr.write(`${report.failure.message}\n`);
} finally {
  await writeFile(
    path.join(output, "screenshots.json"),
    `${JSON.stringify(report, null, 2)}\n`,
  );
  await browser.close();
}
