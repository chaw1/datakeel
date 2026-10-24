import assert from "node:assert/strict";

// Review only the isolated replay demo. The external plan stays unexecuted.
export async function kgSmoke({ page, json, screenshot, checks }) {
  const originalViewport = page.viewportSize();
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page.locator('.sidebar a[href="#/kg"]').click();
  await page.locator(".kg-relations tbody tr").first().waitFor();
  const datasetId = await page
    .getByLabel("Graph dataset", { exact: true })
    .inputValue();
  const versionId = await page
    .getByLabel("Dataset version", { exact: true })
    .inputValue();
  assert.ok(
    (await json("/api/datasets")).some(
      (item) => item.id === datasetId && item.metadata.kg_samples === true,
    ),
  );
  await page.getByLabel("Find an entity", { exact: true }).fill("Vivo");
  await page
    .locator('.kg-relations tbody tr[data-verification="needs_review"]')
    .first()
    .waitFor();
  const row = page
    .locator(".kg-relations tbody tr")
    .filter({ hasText: "Vivo" })
    .first();
  const id = await row.getAttribute("data-relation-id");
  await row.getByRole("button", { name: "Inspect relation" }).click();
  const drawer = page.getByRole("dialog", { name: "Relation source evidence" });
  await drawer.locator(".kg-review-issues li").first().waitFor();
  assert.ok((await drawer.locator(".kg-missing").count()) > 0);
  assert.ok((await drawer.locator("mark").count()) > 0);
  const original = await json(`/api/kg/relations/${id}`);
  assert.equal(original.relation.assertion.verification, "needs_review");
  await screenshot("knowledge-graph-vivo-source", false);
  await drawer.getByRole("button", { name: "Close graph details" }).click();
  await row.getByRole("checkbox").check();
  const decision = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/evidence/assertions/decide") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Reject selected", exact: true })
    .click();
  const action = await (await decision).json();
  assert.equal(action.status, "SUCCEEDED");
  await row.locator(".kg-badge.rejected").waitFor();
  const rejected = await json(`/api/kg/relations/${id}`);
  assert.equal(rejected.relation.assertion.status, "rejected");
  for (const field of [
    "subject",
    "object",
    "anchors",
    "verification",
    "verification_detail",
  ])
    assert.deepEqual(
      rejected.relation.assertion[field],
      original.relation.assertion[field],
    );
  await page.getByRole("tab", { name: "Graph", exact: true }).click();
  await page
    .locator(".kg-edge.rejected")
    .first()
    .waitFor({ state: "attached" });
  await screenshot("knowledge-graph-rejected-graph", false);
  checks.push(
    "KG Vivo retains source evidence and missing endpoint warning; a real batch rejection changes only review status and is shown as a rejected graph edge",
  );

  await page.getByRole("tab", { name: "Relations", exact: true }).click();
  await page.getByLabel("Find an entity", { exact: true }).fill("");
  await page
    .getByLabel("Source verification", { exact: true })
    .selectOption("needs_review");
  await page.locator(".kg-relations tbody tr").first().waitFor();
  assert.ok(
    await page
      .locator(".kg-relations tbody tr")
      .evaluateAll((rows) =>
        rows.every((item) => item.dataset.verification === "needs_review"),
      ),
  );
  await screenshot("knowledge-graph-review-en", false);
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await screenshot("knowledge-graph-review-zh", false);
  await page
    .getByRole("combobox", { name: "语言", exact: true })
    .selectOption("en");
  await page
    .getByLabel("Source verification", { exact: true })
    .selectOption("");
  await page.getByRole("tab", { name: "Entities", exact: true }).click();
  await page
    .getByRole("button", { name: "All source occurrences", exact: true })
    .first()
    .click();
  const entityDrawer = page.getByRole("dialog", {
    name: "All source occurrences",
  });
  await entityDrawer.locator(".kg-source-text mark").first().waitFor();
  await screenshot("knowledge-graph-entity-occurrences", false);
  await entityDrawer
    .getByRole("button", { name: "Close graph details" })
    .click();
  const runs = await json(
    `/api/kg/runs?dataset_id=${datasetId}&version_id=${versionId}`,
  );
  assert.ok(
    runs.some((run) =>
      run.report.failures.some((failure) => failure.reason === "truncated"),
    ),
  );
  await page.getByRole("tab", { name: "Extraction runs", exact: true }).click();
  await page
    .locator(".kg-report summary")
    .filter({ hasText: "replay-demo" })
    .first()
    .click();
  await page.getByText("truncated", { exact: true }).first().waitFor();
  await screenshot("knowledge-graph-partial-report", false);
  await page
    .getByRole("tab", { name: "Schema proposals", exact: true })
    .click();
  await page.locator(".kg-report summary").first().click();
  await page.locator(".kg-report[open] tbody tr").first().waitFor();
  await screenshot("knowledge-graph-schema-proposals", false);

  const runsBefore = await json("/api/actions/runs");
  await page.locator(".kg-extraction > summary").click();
  const profiles = await json("/api/kg/profiles");
  const cloud = profiles.find((profile) => profile.id === "cloud");
  assert.ok(cloud, "The example cloud profile must be present");
  await page
    .getByLabel("Extraction profile", { exact: true })
    .selectOption(cloud.id);
  const prepared = page.waitForResponse((response) =>
    response.url().endsWith("/api/actions/run_kg_extraction/prepare"),
  );
  await page
    .getByRole("button", { name: "Prepare graph extraction", exact: true })
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.external, true);
  assert.equal(plan.status, "PREPARED");
  const card = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  await card
    .getByRole("button", { name: "Approve and extract a knowledge graph" })
    .waitFor();
  assert.ok(plan.impact.kg_estimate.input_tokens > 0);
  await card
    .getByText(plan.impact.kg_estimate.target_host, { exact: true })
    .waitFor();
  if (plan.impact.kg_estimate.cost_upper_usd === null)
    await card.getByText("Unknown", { exact: true }).waitFor();
  assert.equal((await json("/api/actions/runs")).length, runsBefore.length);
  assert.equal(
    (await json(`/api/actions/plans/${plan.id}`)).status,
    "PREPARED",
  );
  await screenshot("knowledge-graph-external-approval", false);
  checks.push(
    "KG entities expose all source occurrences, report exposes the deliberate length failure and schema proposals, bilingual filters render, and cloud prepare shows frozen estimates with zero execution",
  );
  await page.setViewportSize({ width: 390, height: 844 });
  assert.ok(
    await page
      .locator("main")
      .evaluate(
        (main) => main.getBoundingClientRect().width <= globalThis.innerWidth,
      ),
  );
  assert.ok(
    await page.evaluate(
      () =>
        globalThis.document.documentElement.scrollWidth <=
        globalThis.innerWidth,
    ),
    "The mobile page must not overflow horizontally",
  );
  await screenshot("knowledge-graph-mobile", false);
  await page.setViewportSize(originalViewport);
  return {
    datasetId,
    versionId,
    rejectedAssertionId: id,
    decisionRunId: action.id,
    externalPlanId: plan.id,
    externalExecutions: 0,
  };
}
