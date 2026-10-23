import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

// Optional independent paired fixture, imported without scheduling extraction.
// Keep it separate from the canonical 1,000-sample demo and its three review runs.
export async function extractionSmoke({
  page,
  json,
  datasetId,
  screenshot,
  checks,
  viaObject = false,
}) {
  const origin = new URL(page.url()).origin;
  const dataset = await json(`/api/datasets/${datasetId}`);
  assert.equal(dataset.metadata.evidence_samples, true);
  assert.ok(dataset.file_count > 0);
  const files = await json(`/api/datasets/${datasetId}/files`);
  const before = await json(`/api/evidence/assets/${files[0].id}`);
  assert.equal(
    before.assertions.length,
    0,
    "Use a new unextracted paired fixture",
  );
  await page.goto(
    viaObject
      ? `${origin}/#/object/dataset/${encodeURIComponent(datasetId)}?tab=evidence`
      : `${origin}/#/evidence`,
  );
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  if (!viaObject)
    await page
      .getByRole("combobox", { name: "Evidence dataset", exact: true })
      .selectOption(datasetId);
  await page.locator('[data-empty-kind="extraction"]').waitFor();
  const prepared = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/actions/run_pipeline/prepare") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Prepare evidence extraction", exact: true })
    .click();
  const response = await prepared;
  assert.equal(response.status(), 200);
  const plan = await response.json();
  assert.equal(plan.action_type, "run_pipeline");
  assert.equal(plan.reversible, true);
  assert.equal(plan.external, false);
  assert.equal(plan.canonical_params.dataset_id, datasetId);
  assert.equal(plan.canonical_params.version_id, before.source_version);
  assert.equal(plan.canonical_params.shards, 1);
  assert.deepEqual(
    plan.canonical_params.pipeline.nodes
      .filter((node) => node.kind === "operator")
      .map((node) => node.operator),
    [
      "evidence.image_phash",
      "evidence.caption_mentions",
      "evidence.annotation_labels",
      "evidence.label_gap",
      "evidence.near_duplicate",
    ],
  );
  assert.equal(plan.manifest.objects.length, files.length);
  assert.equal(
    await page.getByRole("button", { name: /^Approve and/ }).count(),
    0,
  );
  await screenshot("evidence-extraction-plan");
  const execution = page.waitForResponse(
    (value) =>
      value.url().endsWith(`/api/actions/${plan.id}/execute`) &&
      value.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Execute action", exact: true })
    .click();
  const executeResponse = await execution;
  assert.equal(executeResponse.status(), 200);
  const queued = await executeResponse.json();
  assert.equal(queued.status, "QUEUED");
  assert.ok(queued.task_id);
  const taskLink = page.getByRole("link", {
    name: "Open pipeline task",
    exact: true,
  });
  await taskLink.waitFor();
  assert.equal(
    await taskLink.getAttribute("href"),
    `#/runs?type=pipeline&run=${queued.task_id}`,
  );
  let completed;
  const deadline = Date.now() + 60_000;
  while (Date.now() < deadline) {
    completed = (await json("/api/actions/runs")).find(
      (run) => run.id === queued.id,
    );
    assert.ok(completed);
    if (!["QUEUED", "RUNNING"].includes(completed.status)) break;
    await delay(500);
  }
  assert.equal(completed.status, "SUCCEEDED");
  assert.ok(completed.receipt?.event_id);
  await page.locator(".evidence-sample-row").first().waitFor();
  const after = await json(
    `/api/evidence/assets/${files[0].id}?version_id=${before.source_version}`,
  );
  assert.ok(after.assertions.length > 0);
  assert.equal(after.source_version, before.source_version);
  assert.equal(await page.locator('[data-empty-kind="extraction"]').count(), 0);
  await screenshot("evidence-extraction-complete");
  checks.push(
    "A separate real paired fixture moves from unextracted state through a version-pinned five-operator plan, queued worker execution and successful receipt to visible assertions; no fake-model fallback is involved",
  );
  return {
    entry: viaObject ? "object-evidence" : "evidence-page",
    datasetId,
    sourceVersion: before.source_version,
    planId: plan.id,
    runId: completed.id,
    taskId: queued.task_id,
    eventId: completed.receipt.event_id,
    assertions: after.assertions.length,
  };
}
