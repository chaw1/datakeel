import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";

import { mobileWidth, typographySample } from "./polish-smoke.mjs";

const chapters = {
  en: [
    "Motivation",
    "Composition",
    "Collection",
    "Preprocessing, cleaning and annotation",
    "Uses",
    "Distribution",
    "Maintenance",
  ],
  zh: ["动机", "构成", "采集", "预处理、清洗与标注", "用途", "分发", "维护"],
};

async function language(page, value) {
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/, exact: true })
    .selectOption(value);
}

async function open(page, origin, datasetId) {
  await page.goto(
    `${origin}/#/object/dataset/${encodeURIComponent(datasetId)}?tab=datasheets`,
  );
  await page.locator(".datasheets").waitFor();
}

async function generate(page, json, datasetId, executeLabel) {
  const before = await json(
    `/api/datasets/${encodeURIComponent(datasetId)}/datasheets`,
  );
  const prepared = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/datasets/${datasetId}/datasheets`) &&
      response.request().method() === "POST",
  );
  await page
    .locator(".datasheets .datasheet-controls button.primary")
    .first()
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.action_type, "generate_datasheet");
  assert.equal(plan.reversible && !plan.external, true);
  const card = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  await card.getByRole("button", { name: executeLabel, exact: true }).click();
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const after = await json(
      `/api/datasets/${encodeURIComponent(datasetId)}/datasheets`,
    );
    if (after.length > before.length) return { plan, document: after[0] };
    await delay(250);
  }
  throw new Error("The generated datasheet was not saved");
}

async function checkDocument(page, document, locale) {
  const article = page.locator(".datasheets .datasheet-document").first();
  await article.waitFor();
  assert.equal(
    await page.locator(".datasheets .datasheet-document").count(),
    1,
  );
  const titles = await article
    .locator(".datasheet-chapter h3")
    .allTextContents();
  assert.deepEqual(
    titles.map((title) => title.replace(/^\d+\.\s*/, "")),
    chapters[locale],
  );
  assert.equal(document.sections.length, 7);
  for (const section of document.sections)
    for (const sentence of section.sentences)
      assert.ok(sentence.fact_ids.length > 0, "Every sentence cites facts");
  return article;
}

async function hoverEvidence(page, article, document) {
  const sentence = document.sections
    .flatMap((section) => section.sentences)
    .at(0);
  assert.ok(sentence, "The document retains at least one cited sentence");
  const summary = article.locator(".datasheet-sentence summary").first();
  await summary.hover();
  const title = await summary.getAttribute("title");
  const fact = document.facts.find((item) => item.id === sentence.fact_ids[0]);
  assert.ok(title?.includes(fact.field), "Hover shows the cited field");
  await summary.click();
  const evidence = article.locator(".datasheet-evidence").first();
  await evidence.waitFor();
  await evidence.getByText(fact.id, { exact: true }).waitFor();
  return { sentence: sentence.text, fact: fact.id, field: fact.field };
}

async function downloads(page, article, documentId) {
  const result = {};
  for (const [label, format] of [
    ["Download Markdown", "markdown"],
    ["Download HTML", "html"],
  ]) {
    const link = article.getByRole("link", { name: label, exact: true });
    assert.equal(
      await link.getAttribute("href"),
      `/api/datasheets/${documentId}/download?format=${format}`,
    );
    const waiting = page.waitForEvent("download");
    await link.click();
    const download = await waiting;
    const content = await readFile(await download.path(), "utf8");
    if (format === "markdown") assert.match(content, /^# Dataset datasheet/);
    else {
      assert.match(content, /data-fact-ids="fact-/);
      assert.match(content, /<span class="datasheet-sentence"[^>]* title="/);
      assert.doesNotMatch(content, /<script/i);
    }
    result[format] = {
      filename: download.suggestedFilename(),
      bytes: content.length,
    };
  }
  return result;
}

async function publish(page, json, article, documentId) {
  const prepared = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/datasheets/${documentId}/publish`) &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Publish datasheet", exact: true })
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.reversible, false);
  const runs = await json("/api/actions/runs");
  const card = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  const approve = card.getByRole("button", {
    name: "Approve and publish the datasheet",
    exact: true,
  });
  await approve.waitFor();
  assert.equal((await json(`/api/datasheets/${documentId}`)).published, false);
  assert.equal((await json("/api/actions/runs")).length, runs.length);
  await approve.click();
  await article
    .locator(".datasheet-document-heading")
    .getByText("Published", { exact: true })
    .waitFor();
  assert.equal((await json(`/api/datasheets/${documentId}`)).published, true);
  return plan.id;
}

async function staleRegeneration(page, json, datasetId, latestId) {
  await page.locator(".datasheets").getByText("Out of date").first().waitFor();
  const prepared = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/datasets/${datasetId}/datasheets`) &&
      response.request().method() === "POST",
  );
  const before = await json(`/api/datasets/${datasetId}/datasheets`);
  await page
    .getByRole("button", { name: "Regenerate for latest version", exact: true })
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.canonical_params.version_id, latestId);
  await page
    .locator(`.approval-sheet[data-plan-id="${plan.id}"]`)
    .getByRole("button", { name: "Execute action", exact: true })
    .click();
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    const after = await json(`/api/datasets/${datasetId}/datasheets`);
    if (after.length > before.length) {
      assert.equal(after[0].version_id, latestId);
      assert.equal(after[0].stale, false);
      return after[0];
    }
    await delay(250);
  }
  throw new Error("Regeneration for the latest version was not saved");
}

async function compare(page, previousId) {
  await page
    .getByLabel("Compare with a saved datasheet", { exact: true })
    .selectOption(previousId);
  await page
    .getByRole("heading", { name: "Previous datasheet", exact: true })
    .waitFor();
  const changes = page.getByRole("region", {
    name: "Changes between the two datasheets",
  });
  await changes.getByText(/^Changed chapters:/).waitFor();
  await changes.scrollIntoViewIfNeeded();
  return (await changes.locator("li").count()) > 0;
}

async function modelDraft(page, json, datasetId) {
  await page
    .getByLabel("Writing method", { exact: true })
    .selectOption("model");
  await page.getByLabel("Provider", { exact: true }).selectOption("fake");
  const before = await json(`/api/datasets/${datasetId}/datasheets`);
  const prepared = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/datasets/${datasetId}/datasheets`) &&
      response.request().method() === "POST",
  );
  await page
    .locator(".datasheets .datasheet-controls button.primary")
    .first()
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.canonical_params.mode, "model");
  assert.equal(plan.external, false);
  await page
    .locator(`.approval-sheet[data-plan-id="${plan.id}"]`)
    .getByRole("button", { name: "Execute action", exact: true })
    .click();
  await page.getByText(/^Generation was queued/).waitFor();
  const deadline = Date.now() + 90_000;
  while (Date.now() < deadline) {
    const after = await json(`/api/datasets/${datasetId}/datasheets`);
    if (after.length > before.length) {
      assert.equal(after[0].mode, "model");
      await page
        .getByRole("button", { name: "Refresh datasheets", exact: true })
        .click();
      await page
        .getByLabel("Writing method", { exact: true })
        .selectOption("template");
      return after[0];
    }
    await delay(500);
  }
  throw new Error("The offline model datasheet task did not complete");
}

export async function datasheetSmoke({ page, json, screenshot, checks }) {
  const origin = new URL(page.url()).origin;
  const datasets = await json("/api/datasets");
  const paired = datasets.find(
    (item) => item.name === "Paired scenes · evidence demo",
  );
  const image = datasets.find((item) => item.metadata.image_kg_samples);
  assert.ok(paired && image, "Evidence and image graph demos must exist");
  const versions = await json(`/api/datasets/${paired.id}/versions`);
  versions.sort((left, right) => right.created_at - left.created_at);
  assert.ok(versions.length > 1, "The evidence demo has an older version");
  const [latest, source] = [versions[0], versions.at(-1)];
  await language(page, "en");
  await open(page, origin, paired.id);
  await page
    .getByLabel("Dataset version", { exact: true })
    .selectOption(source.id);
  const first = await generate(page, json, paired.id, "Execute action");
  assert.equal(first.document.version_id, source.id);
  const article = await checkDocument(page, first.document, "en");
  await article
    .getByText("No record of this item exists in the platform.")
    .first()
    .waitFor();
  const hover = await hoverEvidence(page, article, first.document);
  await article.locator(".datasheet-dropped summary").click();
  await article
    .getByText("Every generated sentence passed citation validation.")
    .waitFor();
  const files = await downloads(page, article, first.document.id);
  await article.locator(".datasheet-evidence").first().scrollIntoViewIfNeeded();
  await screenshot("datasheet-evidence-en", false);
  const publication = await publish(page, json, article, first.document.id);
  const regenerated = await staleRegeneration(page, json, paired.id, latest.id);
  const compared = await compare(page, first.document.id);
  await screenshot("datasheet-compare-en", false);
  const typography = await typographySample(page, "datasheet-en");
  const model = await modelDraft(page, json, paired.id);
  await language(page, "zh");
  await open(page, origin, image.id);
  await page.getByLabel("说明书语言", { exact: true }).selectOption("zh");
  const chinese = await generate(page, json, image.id, "执行动作");
  const zhArticle = await checkDocument(page, chinese.document, "zh");
  await zhArticle.getByText("平台中没有这一项的记录。").first().waitFor();
  assert.ok(
    chinese.document.facts.some((fact) => fact.field === "kg.entities"),
    "The image graph datasheet includes graph entity facts",
  );
  await zhArticle.scrollIntoViewIfNeeded();
  await screenshot("datasheet-image-graph-zh", false);
  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await mobileWidth(page, "datasheet-zh-mobile");
  await page.setViewportSize({ width: 1440, height: 1000 });
  await language(page, "en");
  checks.push(
    "Datasheet: seven chapters with missing-fact disclosure, hover and click evidence, empty rejection ledger, Markdown/HTML downloads, approval-gated publication, out-of-date regeneration for the latest version, fact comparison, offline fake model task, Chinese image-graph draft, typography and mobile width",
  );
  return {
    dataset_id: paired.id,
    source_version: source.id,
    latest_version: latest.id,
    template_document: first.document.id,
    hover,
    downloads: files,
    publication_plan: publication,
    regenerated_document: regenerated.id,
    comparison_has_changes: compared,
    model_document: model.id,
    image_document: chinese.document.id,
    typography: typography.samples.length,
    mobile,
  };
}
