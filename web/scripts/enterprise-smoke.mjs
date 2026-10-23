import assert from "node:assert/strict";
import { URLSearchParams } from "node:url";

// Use only the generated local demo. Restore metric changes through its inverse action.
export async function enterpriseSmoke({
  page,
  json,
  post,
  screenshot,
  checks,
}) {
  const primary = "上个季度华东区零售额是多少";
  async function ask(question) {
    await page
      .getByRole("textbox", { name: "Business question", exact: true })
      .fill(question);
    const pending = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/ask") &&
        response.request().method() === "POST",
    );
    await page
      .locator(".ask-composer")
      .getByRole("button", { name: "Ask data", exact: true })
      .click();
    const response = await pending;
    assert.equal(response.status(), 200);
    const answer = await response.json();
    await page.locator(`.ask-answer-${answer.status}`).waitFor();
    return answer;
  }
  async function openAsk() {
    await page
      .locator(".sidebar")
      .getByRole("link", { name: "Ask data", exact: true })
      .click();
    await page.waitForURL((url) => url.hash === "#/ask");
    const heading = page.locator(".ask-page .page-heading h1");
    await heading.waitFor();
    assert.match(await heading.textContent(), /^Ask/);
  }
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "Data catalog", exact: true })
    .click();
  await page.getByRole("heading", { name: /^Data catalog · \d+$/ }).waitFor();
  const [sources, tables, columns, metrics, terms] = await Promise.all(
    ["sources", "tables", "columns", "metrics", "terms"].map((kind) =>
      json(`/api/catalog/${kind}?limit=200`),
    ),
  );
  assert.equal(sources.total, 4);
  assert.ok(
    tables.total >= 20 &&
      columns.total >= 100 &&
      metrics.total >= 12 &&
      terms.total >= 30,
  );
  await page
    .getByRole("region", { name: "Data sources", exact: true })
    .getByRole("button")
    .filter({ hasText: "Fictional Kitchen Co. Ecommerce" })
    .click();
  await page
    .getByRole("region", { name: "Tables", exact: true })
    .getByRole("button")
    .filter({ hasText: "ecommerce/main/orders" })
    .filter({ hasText: /^orders/ })
    .click();
  const fields = page.getByRole("region", { name: "Fields", exact: true });
  await fields.getByRole("heading", { name: "orders", exact: true }).waitFor();
  assert.ok((await fields.locator("tbody tr").count()) >= 8);
  await fields
    .getByRole("button", {
      name: "Downstream impact: paid_amount",
      exact: true,
    })
    .click();
  const impact = page.getByRole("region", {
    name: "Downstream impact",
    exact: true,
  });
  await impact.getByText("retail_revenue", { exact: true }).waitFor();
  const impactResult = await json(
    "/api/catalog/impact?asset_id=ecommerce%2Fmain%2Forders%2Fpaid_amount&max_nodes=100",
  );
  assert.ok(
    impactResult.objects.some((item) => item.asset_ref.asset_type === "metric"),
  );
  assert.ok(
    impactResult.objects.some((item) => item.asset_ref.asset_type === "term"),
  );
  await screenshot("catalog-fields-impact");
  await page
    .getByRole("button", { name: "Business glossary", exact: true })
    .click();
  await page.getByText("1–20 of 32", { exact: true }).waitFor();
  await page
    .locator(".catalog-pagination")
    .getByRole("button", { name: "Next", exact: true })
    .click();
  await page.getByText("21–32 of 32", { exact: true }).waitFor();
  await screenshot("catalog-glossary");
  checks.push(
    "four real catalog sources, table fields, bounded downstream impact and paginated glossary",
  );

  await openAsk();
  await page
    .getByRole("button", {
      name: "East China retail revenue · last quarter",
      exact: true,
    })
    .click();
  assert.equal(
    await page
      .getByRole("textbox", { name: "Business question", exact: true })
      .inputValue(),
    primary,
  );
  const original = await ask(primary);
  assert.equal(original.result.rows[0][0], 4979475);
  assert.equal(original.metric_card.definition.id, "retail_revenue");
  assert.equal(original.reference_instant, "2026-10-01T00:00:00Z");
  assert.ok(original.assertion_ids.length > 0);
  assert.equal(
    await page
      .getByRole("status", { name: "Calculated result", exact: true })
      .textContent(),
    "4,979,475",
  );
  assert.ok(
    (await page.locator(".ask-highlighted-question mark").count()) >= 3,
  );
  const footnotes = page.locator(".ask-provenance .source-footnotes > li");
  assert.ok((await footnotes.count()) >= 4);
  const sourceIds = await footnotes.evaluateAll((items) =>
    items.map((item) => item.dataset.sourceId),
  );
  assert.equal(new Set(sourceIds).size, sourceIds.length);
  assert.equal(
    await page.locator(".ask-number-line .footnote-reference").count(),
    4,
  );
  const termStyles = await page.locator(".ask-term").evaluateAll((items) =>
    items.map((item) => ({
      recognized: item.classList.contains("recognized"),
      decoration:
        item.ownerDocument.defaultView.getComputedStyle(item)
          .textDecorationStyle,
    })),
  );
  assert.ok(
    termStyles.some((item) => item.recognized && item.decoration === "solid"),
  );
  assert.ok(
    termStyles.some((item) => !item.recognized && item.decoration === "dashed"),
  );
  for (const label of [
    "a · Metric definition",
    "c · Source tables and fields",
    "d · Time interval",
  ])
    await page.getByRole("link", { name: label, exact: true }).click();
  assert.equal(new URL(page.url()).hash, "#/ask");
  await page.getByText("[2026-07-01, 2026-10-01)", { exact: true }).waitFor();
  assert.equal(await page.locator(".ask-sql").getAttribute("open"), null);
  await page
    .getByRole("link", { name: "b · SQL and bound parameters", exact: true })
    .click();
  assert.equal(
    await page.locator(".source-footnotes details[open]").count(),
    4,
  );
  await page.locator(".ask-sql pre").first().waitFor();
  assert.match(
    await page.locator(".ask-sql pre").first().textContent(),
    /^SELECT/,
  );
  assert.ok((await page.locator(".ask-source-lists code").count()) >= 4);
  await screenshot("ask-answer-evidence");
  const replayed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/ask/${original.id}`),
  );
  await page
    .getByRole("button", { name: "Replay saved answer", exact: true })
    .click();
  assert.deepEqual(await (await replayed).json(), original);
  await page
    .getByRole("button", { name: "View lineage", exact: true })
    .waitFor();
  const graphResponse = page.waitForResponse((response) =>
    response.url().includes("/api/lineage/graph?asset_id=retail_revenue"),
  );
  await page.getByRole("button", { name: "View lineage", exact: true }).click();
  const graph = await graphResponse;
  const graphUrl = new URL(graph.url());
  for (const [key, value] of [
    ["hops", "2"],
    ["max_nodes", "25"],
    ["include_catalog", "true"],
    ["include_semantic", "true"],
    ["collapse", "true"],
  ])
    assert.equal(graphUrl.searchParams.get(key), value);
  assert.equal(graph.status(), 200);
  const graphData = await graph.json();
  const displayGroups = new Set(
    graphData.nodes.map((node) =>
      node.asset_type === "action_run" && node.display_name
        ? `action_run:${node.display_name}`
        : `asset:${node.id}`,
    ),
  );
  assert.ok(displayGroups.size <= 25);
  await page.waitForURL((url) =>
    url.hash.startsWith("#/object/metric/retail_revenue?"),
  );
  assert.equal(
    new URLSearchParams(new URL(page.url()).hash.split("?")[1]).get("tab"),
    "relations",
  );
  await page
    .getByRole("article", { name: "Object archive", exact: true })
    .waitFor();
  for (const kind of ["metric", "column", "table"])
    await page
      .locator(`.graph-node[data-asset-type="${kind}"]`)
      .first()
      .waitFor({ state: "attached" });
  await page
    .locator(".graph-edge.catalog")
    .first()
    .waitFor({ state: "attached" });
  const positions = await page
    .locator(".graph-node[data-asset-type]")
    .evaluateAll((nodes) =>
      nodes.map((node) => ({
        kind: node.getAttribute("data-asset-type"),
        x: node.closest(".archive-card").getBoundingClientRect().x,
      })),
    );
  assert.ok(new Set(positions.map((item) => item.x)).size >= 3);
  assert.ok(positions.length <= 25);
  for (const label of await page
    .locator(".archive-card-button")
    .allTextContents())
    assert.doesNotMatch(
      label,
      /[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}/i,
    );
  await screenshot("catalog-layered-lineage");
  checks.push(
    "primary answer 4,979,475 with metric version, SELECT, bound parameters, NFC highlights, source fields and exact replay; two-hop catalog graph",
  );

  await openAsk();
  const rejected = [];
  for (const [question, status] of [
    ["退货率为什么上升", "unanswerable"],
    ["下个月市场份额会是多少", "unanswerable"],
    ["客户满意度如何", "unanswerable"],
    ["品牌知名度提高了多少", "unanswerable"],
    ["上个季度营业额是多少", "clarification"],
    ["上个季度出货额和零售额是多少", "clarification"],
  ]) {
    const answer = await ask(question);
    assert.equal(answer.status, status);
    assert.equal(answer.result, null);
    assert.equal(answer.sql, null);
    assert.equal(await page.locator(".ask-scalar, .ask-sql").count(), 0);
    assert.ok(answer.candidates.length >= (status === "unanswerable" ? 3 : 2));
    rejected.push({
      id: answer.id,
      question,
      status,
      candidates: answer.candidates.length,
    });
    await screenshot(`ask-${status}-${rejected.length}`);
    if (status === "clarification") {
      assert.equal(
        await page.locator(".ask-clarification-question").count(),
        1,
      );
      const choices = page.locator(".ask-candidate");
      assert.ok((await choices.count()) >= 2);
      for (const label of await choices.allTextContents()) {
        assert.match(label, /Version \d+/);
        assert.match(label, /Owner:/);
        assert.match(label, /(sum|count|avg|min|max)\(/i);
      }
      const selected = page.waitForResponse(
        (response) =>
          response.url().endsWith("/api/ask") &&
          response.request().method() === "POST",
      );
      await choices.first().click();
      const response = await selected;
      assert.equal(response.status(), 200);
      const request = response.request().postDataJSON();
      assert.equal(request.question, question);
      assert.equal(request.metric_id, answer.candidates[0].definition.id);
      assert.equal(request.reference_instant, answer.reference_instant);
      assert.equal(request.session_id, answer.session_id);
      const resolved = await response.json();
      assert.equal(resolved.status, "answered");
      assert.equal(typeof resolved.result.rows[0][0], "number");
      await page.locator(".ask-answer-answered .answer-number").waitFor();
      rejected.at(-1).resolved = {
        id: resolved.id,
        metricId: request.metric_id,
        value: resolved.result.rows[0][0],
      };
      await screenshot(`ask-clarified-${rejected.length}`);
    } else {
      await page.getByText("Recorded reason", { exact: true }).click();
      await page.getByText(answer.message, { exact: true }).waitFor();
      const writes = [];
      const watchWrite = (request) => {
        if (request.method() === "POST") writes.push(request.url());
      };
      page.on("request", watchWrite);
      await page
        .getByRole("button", {
          name: "Ask the metric owner to add a definition",
          exact: true,
        })
        .click();
      const draft = await page
        .getByRole("textbox", { name: "Metric request draft", exact: true })
        .inputValue();
      assert.ok(draft.includes(question) && draft.includes(answer.message));
      page.off("request", watchWrite);
      assert.equal(writes.length, 0);
    }
  }
  checks.push(
    "all four unanswerable questions preserve reasons and generate local draft text without writes; both clarification questions keep original question and resolve to numeric answers through metric_id",
  );

  await page
    .locator(".sidebar")
    .getByRole("link", { name: "Data catalog", exact: true })
    .click();
  await page.getByRole("button", { name: "Metrics", exact: true }).click();
  await page
    .getByRole("region", { name: "Metrics", exact: true })
    .getByRole("button")
    .filter({ hasText: "retail_revenue" })
    .click();
  await page
    .getByRole("link", { name: "View version history (JSON)", exact: true })
    .waitFor();
  await screenshot("catalog-metric-definition");
  await page
    .getByRole("button", { name: "Edit definition", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "Amount or count field", exact: true })
    .selectOption("ecommerce/main/orders/list_amount");
  const prepared = page.waitForResponse((response) =>
    response.url().endsWith("/api/actions/update_metric/prepare"),
  );
  await page
    .getByRole("button", { name: "Review change", exact: true })
    .click();
  const plan = await (await prepared).json();
  assert.equal(plan.action_type, "update_metric");
  assert.equal(plan.reversible, true);
  const executed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${plan.id}/execute`),
  );
  await page
    .getByRole("button", { name: "Execute action", exact: true })
    .click();
  const run = await (await executed).json();
  assert.equal(run.status, "SUCCEEDED");
  await screenshot("catalog-metric-updated");
  await openAsk();
  const changed = await ask(primary);
  assert.equal(changed.result.rows[0][0], 5255975);
  assert.equal(
    changed.metric_card.definition.version,
    original.metric_card.definition.version + 1,
  );
  await screenshot("ask-updated-definition");
  const rollback = await post("/api/actions/rollback_metric/prepare", {
    metric_id: "retail_revenue",
    version: original.metric_card.definition.version,
  });
  const restored = await post(`/api/actions/${rollback.id}/execute`, {
    plan_digest: rollback.plan_digest,
  });
  assert.equal(restored.status, "SUCCEEDED");
  const afterRollback = await ask(primary);
  assert.equal(afterRollback.result.rows[0][0], original.result.rows[0][0]);
  assert.equal(
    afterRollback.metric_card.definition.version,
    original.metric_card.definition.version + 2,
  );
  const history = await json("/api/catalog/metrics/retail_revenue/history");
  assert.ok(history.audit.some((entry) => entry.plan_id === plan.id));
  checks.push(
    "UI metric editor prepares and executes a reversible action; answer changes 4,979,475 → 5,255,975 and inverse restores it with increasing versions and audit",
  );
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("zh");
  await page.locator(".ask-page .page-heading h1").waitFor();
  assert.match(
    await page.locator(".ask-page .page-heading h1").textContent(),
    /[\u3400-\u9fff]/,
  );
  await screenshot("ask-zh");
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "数据目录", exact: true })
    .click();
  await screenshot("catalog-zh");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload();
  await page
    .locator(".sidebar")
    .getByRole("link", { name: "数据目录", exact: true })
    .click();
  await page
    .getByRole("region", { name: "数据源", exact: true })
    .getByText("ecommerce", { exact: true })
    .waitFor();
  await screenshot("catalog-mobile", false);
  await page.setViewportSize({ width: 1440, height: 1000 });
  checks.push(
    "catalog and ask translate to Chinese; catalog renders at mobile width",
  );
  return {
    counts: {
      sources: sources.total,
      tables: tables.total,
      columns: columns.total,
      metrics: metrics.total,
      terms: terms.total,
    },
    original,
    changed,
    afterRollback,
    rejected,
    graphNodes: positions.length,
    graphRawNodes: graphData.nodes.length,
    planId: plan.id,
    runId: run.id,
    rollbackRunId: restored.id,
  };
}
