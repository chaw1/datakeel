import assert from "node:assert/strict";
import { URLSearchParams } from "node:url";

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
const fixedScene = "val/scene-0817/image.png";

function objectHash(kind, id, params = {}) {
  return `#/object/${kind}/${encodeURIComponent(id)}?${new URLSearchParams({ tab: "relations", ...params })}`;
}
function graphPath(id) {
  return `/api/lineage/graph?${new URLSearchParams({
    asset_id: id,
    hops: "2",
    max_nodes: "25",
    include_catalog: "true",
    include_semantic: "true",
    collapse: "true",
  })}`;
}
function matchingRuns(runs, fileId) {
  return runs.filter(
    (run) =>
      run.action_type === "decide_assertions" &&
      run.status === "SUCCEEDED" &&
      run.receipt?.outputs?.some(
        (ref) => ref.asset_type === "file" && ref.asset_id === fileId,
      ),
  );
}
function timestamp(value) {
  if (typeof value === "number") return value < 1e12 ? value * 1000 : value;
  return new Date(value).getTime();
}
function derivedCount(table) {
  const columns = new Set(
    table.columns.map((column) => column.asset_ref.asset_id),
  );
  return new Set(
    table.neighbors.links
      .filter(
        (link) => link.kind === "derived" && columns.has(link.source.asset_id),
      )
      .map((link) => link.target.asset_id),
  ).size;
}
async function allEvidence(post, datasetId) {
  const items = [];
  let cursor = null;
  do {
    const result = await post("/api/evidence/query", {
      schema_version: "1.1",
      object_type: "file",
      namespace: "default",
      include_deleted: true,
      dataset_id: datasetId,
      version_ids: [],
      limit: 10000,
      page_size: 200,
      sort: "review",
      cursor,
    });
    items.push(...result.items);
    cursor = result.next_cursor;
  } while (cursor);
  return items;
}

// Call after evidenceSmoke and enterpriseSmoke, against the isolated local demo.
// Keep the established evidence fixture's ordering and selectors unchanged.
export async function workspaceSmoke({ page, json, post, screenshot, checks }) {
  const origin = new URL(page.url()).origin;
  assert.ok(
    ["localhost", "127.0.0.1", "[::1]"].includes(new URL(origin).hostname),
    "Workspace smoke is restricted to the isolated loopback demo",
  );
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  const archive = page.getByRole("article", {
    name: "Object archive",
    exact: true,
  });
  async function open(hash) {
    await page.goto(`${origin}/${hash}`);
    await page.waitForURL((url) => url.hash === hash);
  }
  async function openObject(kind, id, params = {}) {
    await open(objectHash(kind, id, params));
    await archive.locator(".object-header h1").waitFor();
    await archive.locator(".object-body").waitFor();
    assert.equal(await archive.getByRole("alert").count(), 0);
  }
  function fact(key) {
    return archive.locator(`[data-fact="${key}"]`);
  }
  async function factValue(key, expected) {
    assert.equal(
      (await fact(key).locator("strong").textContent()).trim(),
      String(expected),
      key,
    );
  }
  async function followFact(key, params, selector) {
    const href = await fact(key).getAttribute("href");
    assert.ok(href?.startsWith("#/"), `${key} must have a genuine destination`);
    const query = new URLSearchParams(href.split("?")[1]);
    for (const [name, value] of Object.entries(params))
      assert.equal(query.get(name), value, key);
    await fact(key).click();
    await page.waitForURL((url) => url.hash === href);
    if (selector) await page.locator(selector).waitFor();
    return { href, query };
  }
  async function historyFact(key, expectedEvent) {
    const { query } = await followFact(
      key,
      { tab: "history" },
      ".object-history",
    );
    const eventId = query.get("event");
    assert.ok(eventId, `${key} must locate an actual event`);
    if (expectedEvent) assert.equal(eventId, expectedEvent);
    const focused = page.locator(".object-event.is-focused");
    await focused.first().waitFor();
    assert.ok((await focused.first().getAttribute("id")).endsWith(eventId));
  }

  const datasets = await json("/api/datasets?include=quality");
  const paired = datasets.find(
    (item) => item.name === "Paired scenes · evidence demo",
  );
  assert.ok(paired, "The isolated paired-scenes demo must be seeded");
  const [files, versions, quality, discovered, metric] = await Promise.all([
    json(`/api/datasets/${paired.id}/files`),
    json(`/api/datasets/${paired.id}/versions`),
    json(`/api/datasets/${paired.id}/quality`),
    json("/api/search?limit=100"),
    json("/api/catalog/metrics/retail_revenue"),
  ]);
  const file = files.find((item) => item.filename === fixedScene);
  assert.ok(file, `The required ${fixedScene} fixture must exist`);
  const sample = await json(`/api/evidence/assets/${file.id}`);
  const review = sample.assertions.find(
    (item) =>
      item.predicate === "mentions" &&
      item.object?.concept === "person" &&
      item.subject.asset_id === file.id,
  );
  assert.ok(review, "The scene must expose a genuine local person assertion");
  const existing = matchingRuns(await json("/api/actions/runs"), file.id);
  assert.ok(
    existing.length <= 3,
    `${fixedScene} already has ${existing.length} review runs; refusing to rewrite immutable history to fake ×3`,
  );
  const created = [];
  for (let index = existing.length; index < 3; index += 1) {
    const status =
      index === 2 ? review.status : index === 0 ? "accepted" : "rejected";
    const plan = await post("/api/actions/decide_assertions/prepare", {
      assertion_ids: [review.id],
      status,
      reason: `Workspace fixed-scene review ${index + 1} of 3`,
    });
    assert.ok(
      plan.manifest.objects.some((item) => item.asset_ref.asset_id === file.id),
    );
    const run = await post(`/api/actions/${plan.id}/execute`, {
      plan_digest: plan.plan_digest,
      operation_id: plan.operation_id,
    });
    assert.equal(run.status, "SUCCEEDED");
    assert.equal(run.action_type, "decide_assertions");
    created.push(run.id);
  }
  const reviewRuns = matchingRuns(await json("/api/actions/runs"), file.id);
  assert.equal(reviewRuns.length, 3);
  const after = await json(
    `/api/evidence/assets/${file.id}?version_id=${sample.source_version}`,
  );
  const reviewed = after.assertions.find((item) => item.id === review.id);
  assert.equal(
    reviewed.status,
    review.status,
    "The smoke must restore the original review status",
  );
  for (const key of [
    "subject",
    "object",
    "anchors",
    "extractor",
    "producer_event_id",
  ])
    assert.deepEqual(reviewed[key], review[key]);
  await openObject("file", file.id, {
    dataset: paired.id,
    version: sample.source_version,
  });
  const group = page.getByRole("button", {
    name: "Inspect decide_assertions",
    exact: true,
  });
  await group.waitFor();
  assert.equal(
    (await group.locator(".archive-multiple").textContent()).trim(),
    "×3",
  );
  assert.ok((await page.locator(".graph-node").count()) <= 25);
  await group.hover();
  const preview = page.getByRole("tooltip");
  await preview.waitFor();
  for (const run of reviewRuns)
    assert.ok((await preview.textContent()).includes(run.id));
  await screenshot("workspace-scene-0817-three-runs-hover", false);
  await group.click();
  const members = page.getByRole("region", {
    name: "decide_assertions · 3 runs",
    exact: true,
  });
  await members.waitFor();
  assert.equal(await members.locator("li").count(), 3);
  assert.equal(
    await members.getByRole("button", { name: /^Copy ID / }).count(),
    3,
  );
  assert.deepEqual(
    (
      await members
        .locator("button[title]")
        .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("title")))
    ).sort(),
    reviewRuns.map((run) => run.id).sort(),
  );
  await screenshot("workspace-scene-0817-three-runs-expanded");
  checks.push(
    "fixed Paired scenes val/scene-0817/image.png has exactly three genuine decide_assertions receipts; ×3 hover exposes every full ID and click expands all three members without changing evidence facts",
  );

  const snapshot = await workbenchChecks({
    page,
    json,
    open,
    screenshot,
    checks,
  });
  const tableId = metric.definition.measure.table;
  const columnId = metric.definition.measure.column;
  const term = discovered.find((item) => item.kind === "term");
  for (const kind of kinds)
    assert.ok(
      discovered.some((item) => item.kind === kind),
      `Search must discover ${kind}`,
    );
  versions.sort((a, b) => timestamp(b.created_at) - timestamp(a.created_at));
  assert.ok(versions.length);
  const targets = [
    ["dataset", paired.id, {}],
    ["file", file.id, { dataset: paired.id, version: sample.source_version }],
    ["version", versions[0].id, { dataset: paired.id }],
    ["action_run", reviewRuns[0].id, {}],
    ["table", tableId, {}],
    ["column", columnId, {}],
    ["metric", metric.definition.id, {}],
    ["term", term.id, {}],
  ];
  for (const [kind, id, params] of targets) {
    await openObject(kind, id, params);
    assert.ok(
      (await archive.locator(".object-header h1").textContent()).trim(),
    );
    assert.ok(
      (await archive.locator(".object-kicker .badge").textContent()).trim(),
    );
    const copy = archive
      .locator(".object-header")
      .getByRole("button", { name: "Copy ID", exact: true });
    assert.equal(await copy.getAttribute("title"), id);
    const businessId = ["table", "column", "metric", "term"].includes(kind);
    if (!businessId)
      assert.match(
        id,
        /^[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}$/i,
      );
    assert.equal(
      await copy.locator("code").textContent(),
      businessId ? id : id.slice(0, 8),
    );
    for (const tab of ["Facts", "Relations", "Evidence", "History"])
      assert.equal(
        await archive
          .locator(".object-tabs")
          .getByRole("link", { name: tab, exact: true })
          .count(),
        1,
      );
    assert.equal(
      await archive.locator('.object-tabs [aria-current="page"]').textContent(),
      "Relations",
    );
    assert.ok((await archive.locator(".object-fact").count()) >= 2);
    await archive
      .getByRole("region", { name: "Relations", exact: true })
      .waitFor();
    await screenshot(`workspace-object-${kind}`, false);
    if (kind === "file") {
      await factValue("objQuality", after.quality_score.toFixed(1));
      await followFact(
        "objQuality",
        { tab: "quality" },
        ".object-file-quality",
      );
      assert.equal(
        await archive.locator(".object-file-quality strong").textContent(),
        after.quality_score.toFixed(1),
      );
      assert.equal(
        await archive.locator(".object-file-quality a").getAttribute("href"),
        objectHash("version", after.source_version, {
          tab: "facts",
          dataset: paired.id,
        }),
      );
      await screenshot("workspace-file-quality-source", false);
    }
  }
  checks.push(
    "all eight search kinds load directly through canonical encoded object routes with type/status, short-ID copy target, factual metadata and shared facts/relations/evidence/history tabs",
  );

  await openObject("dataset", paired.id);
  const samples = await allEvidence(post, paired.id);
  await factValue("objCurrentVersion", versions.length);
  await factValue("objFileCount", paired.file_count);
  await factValue("objQuality", quality.total.toFixed(1));
  await factValue(
    "objCandidates",
    samples.reduce(
      (sum, item) =>
        sum +
        item.assertions.filter((assertion) => assertion.status === "candidate")
          .length,
      0,
    ),
  );
  const current = await followFact(
    "objCurrentVersion",
    { tab: "facts", dataset: paired.id },
    ".object-source-evidence",
  );
  assert.equal(
    current.href.split("?")[0],
    `#/object/version/${encodeURIComponent(versions[0].id)}`,
  );
  await openObject("dataset", paired.id);
  await followFact("objFileCount", { tab: "files" }, ".object-body table");
  assert.equal(
    await archive.locator(".table-toolbar > span").textContent(),
    `${files.length} files`,
  );
  assert.ok(
    (await archive.locator('tbody a[href^="#/object/file/"]').count()) > 0,
  );
  await followFact(
    "objQuality",
    { tab: "quality" },
    ".object-body .quality-content",
  );
  await followFact("objCandidates", { tab: "evidence" }, ".evidence-explorer");
  await historyFact("objUpdated");
  await archive
    .locator(".object-tabs")
    .getByRole("link", { name: "Versions", exact: true })
    .click();
  await archive.locator(".version-list").waitFor();
  assert.equal(await archive.locator(".version-row").count(), versions.length);
  await archive
    .locator(".object-tabs")
    .getByRole("link", { name: "Report", exact: true })
    .click();
  await archive.locator(".report-layout").waitFor();
  const reportHash = new URL(page.url()).hash;
  await archive.locator(".report-index a").first().click();
  assert.equal(
    new URL(page.url()).hash,
    reportHash,
    "Report chapter jumps must preserve object context",
  );
  await screenshot("workspace-dataset-report");
  checks.push(
    "dataset version/file/quality/candidate facts reconcile with real APIs, each fact opens its actual source or focused event, and files/versions/report retain original behavior and chapter context",
  );

  const [table, tableGraph, metricHistory] = await Promise.all([
    json(`/api/catalog/tables/${encodeURIComponent(tableId)}`),
    json(graphPath(tableId)),
    json(
      `/api/catalog/metrics/${encodeURIComponent(metric.definition.id)}/history`,
    ),
  ]);
  await openObject("table", tableId);
  await factValue("objColumns", table.columns.length);
  await factValue("objSource", table.table.source_id);
  await factValue("objDerived", derivedCount(table));
  await factValue("objMetrics", table.metrics.length);
  await followFact(
    "objColumns",
    { tab: "evidence", section: "fields" },
    "#object-section-fields table",
  );
  assert.equal(
    await page.locator("#object-section-fields tbody tr").count(),
    table.columns.length,
  );
  await followFact(
    "objSource",
    { tab: "relations", relation: "source" },
    "#object-section-source",
  );
  const source = await json(
    `/api/catalog/objects/${encodeURIComponent(table.table.source_id)}`,
  );
  await page
    .locator("#object-section-source")
    .getByText(source.name, { exact: true })
    .waitFor();
  assert.ok(
    (await page.locator("#object-section-source").textContent()).includes(
      source.name,
    ),
  );
  await followFact(
    "objDerived",
    { tab: "relations", relation: "derived" },
    ".object-relation-filter",
  );
  await followFact(
    "objMetrics",
    { kind: "metric", table: tableId },
    ".catalog-object-list",
  );
  for (const { locale, heading, names } of [
    {
      locale: "en",
      heading: "Metrics",
      names: ["Order count", "Retail revenue", "Retail units"],
    },
    {
      locale: "zh",
      heading: "指标目录",
      names: table.metrics.map((item) => item.name),
    },
  ]) {
    await page
      .getByRole("combobox", { name: /^(Language|语言)$/ })
      .selectOption(locale);
    await page
      .getByRole("heading", {
        name: `${heading} · ${table.metrics.length}`,
        exact: true,
      })
      .waitFor();
    assert.deepEqual(
      (
        await page.locator(".catalog-object-list button").allTextContents()
      ).sort(),
      names.sort(),
      `Filtered metric names in ${locale}`,
    );
  }
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page
    .getByRole("heading", {
      name: `Metrics · ${table.metrics.length}`,
      exact: true,
    })
    .waitFor();
  checks.push(
    "table metric destinations preserve API names in Chinese and show the exact localized fixture names in English",
  );
  await openObject("table", tableId);
  const imported = [...tableGraph.events]
    .sort((a, b) => (b.occurred_at ?? "").localeCompare(a.occurred_at ?? ""))
    .find((event) => event.operator === "CATALOG_IMPORT");
  assert.ok(imported);
  await historyFact("objImportedAt", imported.event_id);
  await screenshot("workspace-table-import-event");

  await openObject("metric", metric.definition.id);
  await factValue("objRevision", metric.definition.version);
  await factValue("objDimensions", metric.definition.dimensions.length);
  const fields = new Set(
    [
      metric.definition.measure.column,
      metric.definition.time.column,
      ...metric.definition.filters.map((item) => item.column),
    ].filter(Boolean),
  );
  await factValue("objMeasures", fields.size);
  const ownerName = metric.owner_english_name ?? metric.definition.owner;
  await factValue("objOwner", ownerName);
  await followFact("objRevision", { tab: "history" }, ".object-revisions");
  assert.equal(
    await archive.locator(".object-revisions [data-metric-version]").count(),
    metricHistory.versions.length,
  );
  for (const { definition } of metricHistory.versions) {
    const row = archive.locator(
      `[data-metric-version="${definition.version}"]`,
    );
    assert.equal(
      await row
        .getByRole("button", { name: "Roll back to this version", exact: true })
        .count(),
      definition.version === metric.definition.version ? 0 : 1,
    );
  }
  await followFact(
    "objDimensions",
    { tab: "relations", relation: "sliced_by" },
    ".object-relation-filter",
  );
  await followFact(
    "objMeasures",
    { tab: "relations", relation: "measures" },
    ".object-relation-filter",
  );
  await followFact(
    "objOwner",
    { tab: "relations", relation: "owner" },
    "#object-section-owner",
  );
  assert.ok(
    (await page.locator("#object-section-owner").textContent()).includes(
      ownerName,
    ),
  );
  assert.ok(
    metricHistory.audit.length,
    "Enterprise smoke must leave genuine metric audit history",
  );
  await historyFact("objModified", metricHistory.audit.at(-1).event_id);
  await screenshot("workspace-metric-audit-event");
  checks.push(
    "table and metric fact values reconcile with typed detail/graph/history APIs; fields/source/derived/filtered-metrics and revision/dimensions/references/owner/audit links reach their specific source records",
  );

  await legacyChecks({
    page,
    origin,
    archive,
    paired,
    tableId,
    reviewRuns,
    screenshot,
    checks,
  });
  await open("#/workbench");
  await page.getByRole("heading", { name: /^Workbench ·/ }).waitFor();
  return {
    fixedScene: {
      datasetId: paired.id,
      fileId: file.id,
      sourceVersion: sample.source_version,
      reviewRuns: reviewRuns.map((run) => run.id),
      createdRuns: created,
    },
    counts: snapshot,
    objectKinds: kinds,
    tableId,
    metricId: metric.definition.id,
  };
}

async function workbenchChecks({ page, json, open, screenshot, checks }) {
  const [datasets, approvals, tasks, actions] = await Promise.all([
    json("/api/datasets?include=quality"),
    json("/api/approvals"),
    json("/api/tasks"),
    json("/api/actions/runs"),
  ]);
  const running = tasks.filter((task) =>
    ["RUNNING", "PENDING", "QUEUED"].includes(task.state),
  );
  const alerts = datasets.filter(
    (dataset) => dataset.quality_score != null && dataset.quality_score < 60,
  );
  const recent = [...actions]
    .sort((a, b) => timestamp(b.created_at) - timestamp(a.created_at))
    .slice(0, 5);
  await open("#/workbench");
  await page
    .getByRole("heading", {
      name: `Workbench · ${approvals.length + running.length + alerts.length} need attention`,
      exact: true,
    })
    .waitFor();
  const navigation = page.getByRole("navigation", {
    name: "Main navigation",
    exact: true,
  });
  const groups = [
    ["workbench", ["workbench"]],
    ["dataGroup", ["datasets", "catalog", "standards", "ask"]],
    ["evidenceGroup", ["evidence", "kg", "quality", "quality-rules"]],
    ["operationsGroup", ["custom-operators", "workflows", "approvals", "runs"]],
    ["agentsGroup", ["agent", "memory", "traces"]],
    ["modelsGroup", ["ontology"]],
  ];
  assert.equal(await navigation.locator("[data-nav-group]").count(), 6);
  for (const [name, routes] of groups) {
    const group = navigation.locator(`[data-nav-group="${name}"]`);
    assert.ok((await group.locator(".nav-label").textContent()).trim());
    assert.deepEqual(
      await group
        .locator("a")
        .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href"))),
      routes.map((route) => `#/${route}`),
    );
  }
  for (const href of await navigation
    .locator("a")
    .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href"))))
    assert.doesNotMatch(href, /(?:lineage|reports?|tasks|action-?runs)/);
  assert.equal(
    await navigation
      .locator("[data-pending-count]")
      .getAttribute("data-pending-count"),
    String(approvals.length),
  );
  for (const [name, title, href] of [
    [
      "approvals",
      `Pending approval · ${approvals.length}`,
      "#/approvals?status=pending",
    ],
    [
      "runs",
      `Running pipelines · ${running.length}`,
      "#/runs?type=pipeline&state=active",
    ],
    [
      "quality",
      `Quality alerts · ${alerts.length} ${alerts.length === 1 ? "dataset" : "datasets"}`,
      "#/quality?filter=alerts",
    ],
  ]) {
    const section = page.locator(`[data-workbench="${name}"]`);
    await section.getByRole("heading", { name: title, exact: true }).waitFor();
    assert.equal(await section.locator("header a").getAttribute("href"), href);
  }
  assert.equal(
    await page.locator('[data-workbench="approvals"] li').count(),
    Math.min(5, approvals.length),
  );
  assert.equal(
    await page
      .locator('[data-workbench="runs"] > ul')
      .first()
      .locator("li")
      .count(),
    Math.min(5, running.length),
  );
  assert.deepEqual(
    await page
      .locator('[data-workbench="runs"] > ul')
      .last()
      .locator("a")
      .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href"))),
    recent.map((run) => objectHash("action_run", run.id)),
  );
  assert.deepEqual(
    (
      await page
        .locator('[data-workbench="quality"] li a')
        .evaluateAll((nodes) => nodes.map((node) => node.getAttribute("href")))
    ).sort(),
    alerts
      .map((dataset) => objectHash("dataset", dataset.id, { tab: "quality" }))
      .sort(),
  );
  await screenshot("workspace-workbench-counts");
  checks.push(
    "six sidebar groups expose no standalone lineage/report/task/action-run pages; workbench totals, approval badge, running pipelines, recent five actions and low-quality dataset alerts match API records and filtered destinations",
  );
  return {
    approvals: approvals.length,
    running: running.length,
    qualityDatasets: alerts.length,
    recentActionIds: recent.map((run) => run.id),
  };
}

async function legacyChecks({
  page,
  origin,
  archive,
  paired,
  tableId,
  reviewRuns,
  screenshot,
  checks,
}) {
  for (const [path, kind, id, params] of [
    [
      `/lineage?asset=${encodeURIComponent(paired.id)}`,
      "dataset",
      paired.id,
      { tab: "relations" },
    ],
    [
      `/lineage?asset_id=${encodeURIComponent(tableId)}&include_catalog=true`,
      "table",
      tableId,
      { tab: "relations" },
    ],
    [
      `/lineage?asset=${encodeURIComponent(reviewRuns[0].id)}&event=${encodeURIComponent(reviewRuns[0].receipt.event_id)}`,
      "action_run",
      reviewRuns[0].id,
      { tab: "relations", event: reviewRuns[0].receipt.event_id },
    ],
    [
      `/report?dataset=${encodeURIComponent(paired.id)}`,
      "dataset",
      paired.id,
      { tab: "report" },
    ],
  ]) {
    const response = await page.goto(`${origin}${path}`);
    assert.equal(response.status(), 200, path);
    await page.waitForURL(
      (url) =>
        url.hash.split("?")[0] === `#/object/${kind}/${encodeURIComponent(id)}`,
    );
    await archive.locator(".object-header h1").waitFor();
    const query = new URLSearchParams(new URL(page.url()).hash.split("?")[1]);
    for (const [key, value] of Object.entries(params))
      assert.equal(query.get(key), value);
    assert.equal(new URL(page.url()).pathname, "/");
  }
  for (const [path, expected] of [
    ["/tasks", "#/runs?type=pipeline"],
    ["/action-runs", "#/runs?type=action"],
    ["/report", "#/datasets"],
    ["/lineage?asset=missing-workspace-smoke-object", "#/datasets"],
  ]) {
    const response = await page.goto(`${origin}${path}`);
    assert.equal(response.status(), 200);
    await page.waitForURL(
      (url) => url.hash === expected && url.pathname === "/",
    );
    await page.locator("main h1").waitFor();
  }
  await screenshot("workspace-legacy-fallback");
  checks.push(
    "HTTP /lineage preserves dataset/table/action identity and receipt event in canonical object relations; /report opens dataset report; /tasks and /action-runs redirect to typed runs; missing legacy context returns to datasets",
  );
}
