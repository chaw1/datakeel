import assert from "node:assert/strict";

// Exercise generated local fixtures only; no model or source registration is performed.
export async function standardsSmoke({ page, json, screenshot, checks }) {
  const origin = new URL(page.url());
  assert.equal(origin.protocol, "http:");
  assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(origin.hostname));
  const locale = page.getByRole("combobox", { name: /^(Language|语言)$/ });
  await locale.selectOption("en");
  await page.locator('.sidebar a[href="#/standards"]').click();
  await page.locator(".standards-page h1").waitFor();
  const root = page.locator(".standards-page");
  const schema = await json("/api/standards/schema");
  assert.equal(schema.additionalProperties, false);
  assert.ok(schema.$defs.FieldStandard && schema.$defs.CodeList);
  const definitions = await json("/api/standards/fields?status=active");
  const codeLists = await json("/api/standards/code-lists?status=active");
  assert.ok(definitions.some((item) => item.code === "customer_id"));
  assert.ok(codeLists.some((item) => item.entries.length > 0));
  await root.getByLabel("Search standards or code lists").fill("customer_id");
  await root.getByLabel("Filter standard status").selectOption("active");
  await root
    .locator(".catalog-object-list button")
    .filter({ hasText: "customer_id" })
    .click();
  await root.locator(".catalog-definition").waitFor();
  assert.match(
    await root.locator(".catalog-definition").innerText(),
    /Data type/,
  );
  await screenshot("standards-fields-en");

  await root.getByRole("button", { name: "Code lists", exact: true }).click();
  const codeList = codeLists.find((item) => item.entries.length > 0);
  await root
    .locator(".catalog-object-list button")
    .filter({ hasText: codeList.code })
    .click();
  await root.locator(".catalog-detail tbody tr").first().waitFor();
  assert.equal(
    await root.locator(".catalog-detail tbody tr").count(),
    codeList.entries.length,
  );
  await screenshot("standards-code-list-en");

  const beforeMappings = await json("/api/standards/mappings");
  const mapped = new Set(beforeMappings.map((item) => item.column_id));
  const suggestions = await json("/api/standards/suggestions");
  const suggestion = suggestions.find(
    (item) => !mapped.has(item.column_id) && item.candidates.length > 0,
  );
  assert.ok(
    suggestion,
    "The enterprise fixture needs an unconfirmed rule candidate",
  );
  const candidate = suggestion.candidates[0];
  await root
    .getByRole("button", { name: "Mapping suggestions", exact: true })
    .click();
  await root.getByLabel("Search columns").fill(suggestion.column_id);
  const matching = root
    .locator(".standards-candidate")
    .filter({ hasText: candidate.standard_code })
    .first();
  await matching.getByRole("list", { name: "Scoring reasons" }).waitFor();
  async function prepare() {
    const prepared = page.waitForResponse((response) =>
      response.url().endsWith("/api/actions/confirm_standard_mapping/prepare"),
    );
    await matching.getByRole("button", { name: "Review mapping" }).click();
    const response = await prepared;
    assert.equal(response.status(), 200);
    const plan = await response.json();
    assert.equal(plan.reversible, true);
    assert.equal(plan.external, false);
    assert.deepEqual(plan.canonical_params.mapping, {
      column_id: suggestion.column_id,
      standard_code: candidate.standard_code,
    });
    return plan;
  }
  const rejectedPlan = await prepare();
  const rejectedCard = root.locator(`[data-plan-id="${rejectedPlan.id}"]`);
  assert.deepEqual(await json("/api/standards/mappings"), beforeMappings);
  await screenshot("standards-mapping-plan-en");
  const rejected = page.waitForResponse((response) =>
    response.url().endsWith(`/api/approvals/${rejectedPlan.id}`),
  );
  await rejectedCard
    .getByRole("button", { name: "Return", exact: true })
    .click();
  assert.equal((await rejected).status(), 200);
  await rejectedCard
    .getByText("The plan was rejected. No action was executed.")
    .waitFor();
  assert.deepEqual(await json("/api/standards/mappings"), beforeMappings);
  const approvedPlan = await prepare();
  const approvedCard = root.locator(`[data-plan-id="${approvedPlan.id}"]`);
  const approval = page.waitForResponse((response) =>
    response.url().endsWith(`/api/approvals/${approvedPlan.id}`),
  );
  const executed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${approvedPlan.id}/execute`),
  );
  await approvedCard
    .getByRole("button", {
      name: "Approve and Confirm standard mapping",
      exact: true,
    })
    .click();
  assert.equal((await approval).status(), 200);
  const run = await (await executed).json();
  assert.equal(run.status, "SUCCEEDED");
  const afterMappings = await json("/api/standards/mappings");
  assert.ok(
    afterMappings.some(
      (item) =>
        item.column_id === suggestion.column_id &&
        item.standard_code === candidate.standard_code,
    ),
  );
  assert.equal(afterMappings.length, beforeMappings.length + 1);
  checks.push(
    "standards rules explain candidates; prepare and reject leave mappings unchanged; explicit approval confirms exactly one mapping",
  );

  await root.getByRole("button", { name: "Coverage", exact: true }).click();
  const coverage = await json("/api/standards/coverage");
  await root.getByRole("heading", { name: /^Violation Top/ }).waitFor();
  for (const group of ["sources", "tables", "owners"]) {
    await root.getByLabel("Group coverage by").selectOption(group);
    assert.equal(
      await root.locator("table").first().locator("tbody tr").count(),
      coverage[group].length,
    );
  }
  await screenshot("standards-coverage-en");
  await root
    .getByRole("button", { name: "Change history", exact: true })
    .click();
  await root.getByText("Current revision", { exact: true }).waitFor();
  const history = await json("/api/standards/history");
  assert.ok(history.revisions.some((item) => item.plan_id === approvedPlan.id));
  await root
    .getByRole("button", { name: "Standards report", exact: true })
    .click();
  await root
    .getByRole("heading", { name: "Field quality", exact: true })
    .waitFor();
  await root.locator(".report-chapter").first().waitFor();
  assert.ok((await root.locator(".report-chapter").count()) >= 4);
  await screenshot("standards-report-en");

  await locale.selectOption("zh");
  for (const [tab, content] of [
    ["字段标准", ".catalog-object-list button"],
    ["码表", ".catalog-object-list button"],
    ["映射建议", ".standards-candidates > li"],
    ["覆盖率", ".standards-summary"],
    ["变更历史", ".metric-history-version"],
    ["落标报告", ".report-chapter"],
  ]) {
    await root.getByRole("button", { name: tab, exact: true }).click();
    await root.locator(content).first().waitFor();
  }
  await screenshot("standards-report-zh");
  const fonts = await root
    .locator("h1,h2,h3,button,label,td,dt,dd")
    .evaluateAll((elements) =>
      elements
        .filter((item) => item.getBoundingClientRect().height > 0)
        .map((item) =>
          Number.parseFloat(
            item.ownerDocument.defaultView.getComputedStyle(item).fontSize,
          ),
        ),
    );
  assert.ok(fonts.every((size) => size >= 12));
  const dirty = coverage.violation_top.find((item) =>
    item.column_id.includes("dirty_customers"),
  );
  assert.ok(dirty, "The generated standards fixture has deliberate violations");
  const tableId = dirty.column_id.split("/").slice(0, -1).join("/");
  await page.goto(
    `${origin.origin}/#/object/table/${encodeURIComponent(tableId)}?tab=facts`,
  );
  await page.getByRole("region", { name: "落标检查", exact: true }).waitFor();
  await page.locator(".standards-checks details").first().waitFor();
  await screenshot("standards-catalog-checks-zh");
  await locale.selectOption("en");
  checks.push(
    "standards six tabs render in English and Chinese with token typography, typed code values, grouped coverage, violation ranking, field quality, history and catalog conformance evidence",
  );
  return {
    rejectedPlanId: rejectedPlan.id,
    approvedPlanId: approvedPlan.id,
    runId: run.id,
    mapping: {
      column_id: suggestion.column_id,
      standard_code: candidate.standard_code,
    },
    coverage,
    revisions: history.revisions.length,
  };
}
