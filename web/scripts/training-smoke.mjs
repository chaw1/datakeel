import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { mobileWidth, typographySample } from "./polish-smoke.mjs";

export async function trainingSmoke({ page, json, screenshot, checks }) {
  const origin = new URL(page.url()).origin;
  const datasets = await json("/api/datasets");
  const dataset = datasets.find((item) => item.metadata.annotation_qa_demo);
  assert.ok(dataset, "The generated annotation dataset exists");
  const versions = await json(`/api/datasets/${dataset.id}/versions`);
  const version = versions[0];
  assert.ok(version);
  const endpoint = `/api/datasets/${dataset.id}/versions/${version.id}/training`;
  const before = await json(`${endpoint}/splits`);
  await page.goto(`${origin}/#/object/dataset/${dataset.id}?tab=versions`);
  const section = page.getByRole("region", {
    name: "Training sets",
    exact: true,
  });
  await section.waitFor();
  await section
    .getByLabel("Training source version", { exact: true })
    .selectOption(version.id);
  const name = `training-ui-${Date.now()}`;
  await section.getByLabel("Split set name", { exact: true }).fill(name);
  const previewResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `${endpoint}/preview` &&
      response.request().method() === "POST",
  );
  await section
    .getByRole("button", { name: "Preview distribution", exact: true })
    .click();
  const preview = await (await previewResponse).json();
  await section
    .getByText("Preview only. Save the split to enable export.", {
      exact: true,
    })
    .waitFor();
  assert.equal((await json(`${endpoint}/splits`)).length, before.length);
  assert.equal(preview.members.length, version.file_count);
  async function save() {
    const response = page.waitForResponse(
      (value) =>
        new URL(value.url()).pathname === `${endpoint}/splits` &&
        value.request().method() === "POST",
    );
    await section
      .getByRole("button", { name: "Save immutable split", exact: true })
      .click();
    const saved = await (await response).json();
    await section
      .getByRole("heading", { name: saved.request.name, exact: true })
      .waitFor();
    await section
      .getByRole("button", { name: "Review export plan", exact: true })
      .waitFor();
    return saved;
  }
  const first = await save();
  assert.deepEqual(first.members, preview.members);
  assert.equal(first.request.seed, 42);
  await section
    .getByLabel("Split set name", { exact: true })
    .fill(`${name}-seed-7`);
  await section.getByLabel("Random seed", { exact: true }).fill("7");
  const second = await save();
  await section
    .getByLabel("Compare with another split", { exact: true })
    .selectOption(first.id);
  await section
    .getByRole("heading", { name: "Distribution comparison", exact: true })
    .waitFor();
  assert.equal(
    await section
      .getByRole("table", { name: "Class distribution", exact: true })
      .count(),
    2,
  );
  assert.ok((await section.getByRole("meter").count()) > 0);
  const leakageResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
      `${endpoint}/splits/${second.id}/leakage`,
  );
  await section
    .getByRole("button", { name: "Check leakage", exact: true })
    .click();
  const leakage = await (await leakageResponse).json();
  assert.deepEqual(leakage.pairs, []);
  await section
    .getByText("No cross-set leakage found within the configured thresholds.", {
      exact: true,
    })
    .waitFor();
  const typography = await typographySample(page, "training-en");
  for (const theme of ["light", "dark"]) {
    await page
      .getByRole("combobox", { name: "Theme", exact: true })
      .selectOption(theme);
    await section.locator(".training-detail").scrollIntoViewIfNeeded();
    await screenshot(`training-distribution-${theme}`, false);
  }
  await section
    .getByLabel("Compare with another split", { exact: true })
    .selectOption("");
  await section
    .getByLabel("Training format", { exact: true })
    .selectOption("coco");
  const annotatorIds = [
    ...new Set(
      second.members.flatMap((member) =>
        member.annotations.map((record) => record.annotator_id),
      ),
    ),
  ].sort();
  assert.ok(annotatorIds.length > 0, "Frozen training annotations exist");
  await section
    .getByLabel("Annotation author", { exact: true })
    .selectOption(annotatorIds[0]);
  await section
    .getByLabel("Archive filename", { exact: true })
    .fill(`training-ui-${second.id}.tar.gz`);
  const preparedResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        "/api/actions/export_dataset/prepare" &&
      response.request().method() === "POST",
  );
  await section
    .getByRole("button", { name: "Review export plan", exact: true })
    .click();
  const plan = await (await preparedResponse).json();
  assert.equal(plan.canonical_params.version_id, version.id);
  assert.equal(plan.canonical_params.split_set_id, second.id);
  assert.equal(plan.canonical_params.format, "coco");
  assert.equal(plan.canonical_params.annotator_id, annotatorIds[0]);
  const card = section.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  const runResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === `/api/actions/${plan.id}/execute` &&
      response.request().method() === "POST",
  );
  await card
    .getByRole("button", {
      name: /^(Execute action|Approve and export dataset)$/,
    })
    .click();
  const run = await (await runResponse).json();
  assert.equal(run.status, "SUCCEEDED");
  const downloadEvent = page.waitForEvent("download");
  await section
    .getByRole("link", { name: "Download training archive", exact: true })
    .click();
  const download = await downloadEvent;
  const bytes = await readFile(await download.path());
  assert.equal(bytes[0], 0x1f);
  assert.equal(bytes[1], 0x8b);
  assert.ok(bytes.length > 100);
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await page.getByRole("heading", { name: "训练集", exact: true }).waitFor();
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await mobileWidth(page, "training-zh-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page
    .getByRole("combobox", { name: "主题", exact: true })
    .selectOption("light");
  await page
    .getByRole("combobox", { name: "语言", exact: true })
    .selectOption("en");
  checks.push(
    "Training sets: read-only preview, immutable named saves, seed configuration, class tables and charts, saved comparison, leakage report, controlled version-bound COCO export and archive download, light/dark themes, Chinese translation, typography and mobile width",
  );
  return {
    dataset_id: dataset.id,
    version_id: version.id,
    first_split: first.id,
    second_split: second.id,
    sample_count: second.members.length,
    leakage_pairs: leakage.pairs.length,
    export_plan: plan.id,
    exported_bytes: bytes.length,
    typography_samples: typography.samples.length,
    mobile,
  };
}
