// Exercise generated release fixtures through the local UI and an offline recipient.
// node scripts/release-smoke.mjs http://127.0.0.1:8816 OUTPUT_DIRECTORY
import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { spawnSync } from "node:child_process";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

import { appearance, localBase } from "./screenshots-helpers.mjs";

const base = localBase(process.argv[2] ?? "http://127.0.0.1:8816");
assert.ok(process.argv[3], "Pass an evidence output directory");
const output = path.resolve(process.argv[3]);
await mkdir(output, { recursive: true });
const report = {
  startedAt: new Date().toISOString(),
  errors: [],
  blocked: [],
  steps: [],
};
const browser = await chromium.launch({
  headless: true,
  ...(process.platform === "darwin" ? { channel: "chrome" } : {}),
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1000 },
  acceptDownloads: true,
  serviceWorkers: "block",
});
const page = await context.newPage();
page.setDefaultTimeout(20_000);
page.on("pageerror", (error) => report.errors.push(error.message));
page.on("console", (message) => {
  if (message.type() === "error") report.errors.push(message.text());
});
await context.route("**/*", async (route) => {
  if (new URL(route.request().url()).origin !== base.origin) {
    report.blocked.push(route.request().url());
    await route.abort("blockedbyclient");
  } else await route.continue();
});
async function api(endpoint, data) {
  const url = new URL(endpoint, base);
  assert.equal(url.origin, base.origin);
  const response =
    data === undefined
      ? await context.request.get(url.href)
      : await context.request.post(url.href, { data });
  assert.ok(
    response.ok(),
    `${endpoint}: ${response.status()} ${await response.text()}`,
  );
  return response.json();
}
async function capture(name) {
  await page.screenshot({
    path: path.join(output, `${name}.png`),
    fullPage: true,
  });
  await writeFile(
    path.join(output, `${name}.txt`),
    await page.locator("body").innerText(),
  );
}
function recipient(source) {
  const run = spawnSync(
    "uv",
    [
      "run",
      "datakeel",
      "reconcile",
      source,
      "--manifest",
      "MANIFEST.json",
      "--json",
    ],
    {
      cwd: fileURLToPath(new URL("../../", import.meta.url)),
      env: {
      PATH: process.env.PATH ?? "/usr/bin:/bin",
        DATAKEEL_DATABASE_URL: "unsupported://offline",
        NO_COLOR: "1",
      },
      encoding: "utf8",
    },
  );
  assert.ok(!run.error, run.error?.message);
  return { code: run.status, report: JSON.parse(run.stdout) };
}
try {
  const dataset = await api("/api/datasets", {
    name: "Generated delivery walkthrough",
    metadata: { purpose: "generated release validation" },
    files: ["alpha.txt", "beta.txt", "gamma.txt"].map((filename) => ({
      filename,
      content_base64: Buffer.from(`Generated payload: ${filename}\n`).toString(
        "base64",
      ),
    })),
  });
  const initial = (await api(`/api/datasets/${dataset.id}/versions`))[0];
  for (const names of [["alpha.txt"], ["alpha.txt", "beta.txt"]]) {
    const plan = await api(
      "/api/actions/create_version_from_selection/prepare",
      {
        selection: {
          dataset_id: dataset.id,
          version_ids: [initial.id],
          filters: [{ field: "filename", operator: "in", value: names }],
        },
      },
    );
    const run = await api(`/api/actions/${plan.id}/execute`, {
      plan_digest: plan.plan_digest,
      actor: "local",
      operation_id: plan.operation_id,
    });
    assert.equal(run.status, "SUCCEEDED");
  }
  const versions = await api(`/api/datasets/${dataset.id}/versions`);
  const before = versions.find((version) => version.file_count === 1);
  const after = versions.find((version) => version.file_count === 2);
  assert.ok(before && after);
  report.fixture = { dataset: dataset.id, before: before.id, after: after.id };
  const href = `${base.origin}/#/object/dataset/${dataset.id}?tab=versions`;
  await page.goto(href);
  await appearance(page, "en", "light");
  await page.getByRole("heading", { name: "Compare versions" }).waitFor();
  await page
    .getByLabel("Before version", { exact: true })
    .selectOption(before.id);
  await page
    .getByLabel("After version", { exact: true })
    .selectOption(after.id);
  await page
    .getByRole("button", { name: "Compare versions", exact: true })
    .click();
  await page.getByRole("button", { name: "Added · 1", exact: true }).waitFor();
  await page
    .getByRole("button", { name: "Unchanged · 1", exact: true })
    .waitFor();
  report.steps.push(
    "Two generated versions compared: added=1, unchanged=1, others=0",
  );
  await capture("release-diff-en");
  await page.getByText("Publish a release", { exact: true }).click();
  await page
    .getByLabel("Source version", { exact: true })
    .selectOption(after.id);
  const tag = `v1.0.0-smoke.${Date.now()}`;
  await page.getByLabel("Semantic version tag", { exact: true }).fill(tag);
  await page
    .getByLabel("Release notes", { exact: true })
    .fill("Reviewed generated files");
  await page
    .getByRole("button", { name: "Review release plan", exact: true })
    .click();
  await page
    .getByRole("button", { name: "Approve and publish release", exact: true })
    .waitFor();
  assert.equal((await api(`/api/datasets/${dataset.id}/releases`)).length, 0);
  await capture("release-approval-en");
  await page
    .getByRole("button", { name: "Approve and publish release", exact: true })
    .click();
  await page.getByRole("button", { name: tag, exact: true }).click();
  await page
    .getByRole("button", { name: "Export delivery package", exact: true })
    .waitFor();
  const release = (await api(`/api/datasets/${dataset.id}/releases`))[0];
  assert.equal(release.version_id, after.id);
  report.release = release;
  const downloadEvent = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "Export delivery package", exact: true })
    .click();
  const archive = path.join(output, "delivery.tar.gz");
  await (await downloadEvent).saveAs(archive);
  const pristine = recipient(archive);
  assert.equal(pristine.code, 0);
  assert.equal(pristine.report.categories.length, 6);
  assert.ok(pristine.report.categories.every((category) => category.passed));
  await writeFile(
    path.join(output, "recipient-pristine.json"),
    JSON.stringify(pristine, null, 2),
  );
  const received = path.join(output, "received");
  await mkdir(received, { recursive: true });
  const unpack = spawnSync("tar", ["-xzf", archive, "-C", received], {
    encoding: "utf8",
  });
  assert.equal(unpack.status, 0, unpack.stderr);
  const manifest = JSON.parse(
    await readFile(path.join(received, "MANIFEST.json"), "utf8"),
  );
  const payload = path.join(received, manifest.files[0].path);
  const bytes = await readFile(payload);
  bytes[0] ^= 1;
  await writeFile(payload, bytes);
  const broken = recipient(received);
  assert.equal(broken.code, 1);
  assert.equal(
    broken.report.categories.find((category) => category.name === "hashes")
      .passed,
    false,
  );
  assert.equal(
    broken.report.categories.find((category) => category.name === "bytes")
      .passed,
    true,
  );
  await writeFile(
    path.join(output, "recipient-corrupted.json"),
    JSON.stringify(broken, null, 2),
  );
  report.steps.push(
    "Approved through UI, downloaded tar, offline pristine passes six categories, one-byte corruption fails hashes",
  );
  await page
    .getByRole("button", { name: "Reconcile stored objects", exact: true })
    .click();
  await page
    .getByRole("heading", { name: "Content hashes · Passed", exact: true })
    .waitFor();
  const archived = await api(`/api/releases/${release.id}/reconciliations`);
  assert.equal(archived.length, 1);
  assert.equal(archived[0].passed, true);
  await capture("release-reconciliation-en");
  await page.reload();
  await page.getByRole("button", { name: tag, exact: true }).click();
  await page
    .getByRole("heading", { name: "Lineage references · Passed", exact: true })
    .waitFor();
  await appearance(page, "zh", "dark");
  await page
    .getByRole("heading", { name: "血缘引用 · 通过", exact: true })
    .waitFor();
  await capture("release-reconciliation-zh");
  report.steps.push(
    "Archived platform check persists after reload and displays in Chinese dark theme",
  );
  assert.deepEqual(report.errors, []);
  assert.deepEqual(report.blocked, []);
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  await capture("failure");
  report.failure = error instanceof Error ? error.stack : String(error);
  process.stderr.write(`${report.failure}\n`);
  process.exitCode = 1;
} finally {
  report.finishedAt = new Date().toISOString();
  await writeFile(
    path.join(output, "release-ui-smoke.json"),
    JSON.stringify(report, null, 2),
  );
  await browser.close();
}
