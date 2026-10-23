import assert from "node:assert/strict";
import { URLSearchParams } from "node:url";

// Every mutation runs through the same UI and Action endpoints as the product.
export async function evidenceSmoke({ page, json, post, screenshot, checks }) {
  const originalViewport = page.viewportSize();
  let lastQuery;
  await page.setViewportSize({ width: 1440, height: 900 });
  async function queryAfter(change) {
    const pending = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/evidence/query") &&
        response.request().method() === "POST",
    );
    await change();
    const response = await pending;
    assert.equal(response.status(), 200);
    lastQuery = response.request().postDataJSON();
    const result = await response.json();
    await page
      .getByText(
        `${result.total} matching ${result.total === 1 ? "sample" : "samples"}`,
        { exact: true },
      )
      .waitFor();
    return result;
  }
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  const initial = await queryAfter(() =>
    page
      .locator(".sidebar")
      .getByRole("link", { name: "Evidence", exact: true })
      .click(),
  );
  assert.equal(initial.total, 1000);
  assert.equal(lastQuery.sort, "review");
  await page.evaluate(() => globalThis.document.fonts.ready);
  const density = {};
  for (const locale of ["en", "zh"]) {
    await page
      .getByRole("combobox", { name: /^(Language|语言)$/ })
      .selectOption(locale);
    await page.evaluate(() => globalThis.scrollTo(0, 0));
    density[locale] = await page
      .locator(".evidence-sample-row")
      .evaluateAll((rows) => ({
        heights: rows.map((row) => row.getBoundingClientRect().height),
        fullyVisible: rows.filter((row) => {
          const bounds = row.getBoundingClientRect();
          return bounds.top >= 0 && bounds.bottom <= globalThis.innerHeight;
        }).length,
      }));
    assert.ok(
      density[locale].fullyVisible >= 6,
      `${locale}: six complete samples fit at 1440 × 900`,
    );
    assert.ok(density[locale].heights.every((height) => height <= 120));
    await screenshot(`evidence-density-${locale}`, false);
  }
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page.setViewportSize(originalViewport);
  const secondReviewPage = await queryAfter(() =>
    page.getByRole("button", { name: "Next page", exact: true }).click(),
  );
  const reviewRanks = [...initial.items, ...secondReviewPage.items].map(
    (item) => [
      item.assertions.filter(
        (assertion) => assertion.object?.value === "unknown",
      ).length,
      item.assertions.filter((assertion) => assertion.status === "candidate")
        .length,
    ],
  );
  for (let index = 1; index < reviewRanks.length; index++) {
    const previous = reviewRanks[index - 1];
    const current = reviewRanks[index];
    assert.ok(
      previous[0] > current[0] ||
        (previous[0] === current[0] && previous[1] >= current[1]),
      "Review priority remains monotonic across the page boundary",
    );
  }
  const filenames = await queryAfter(() =>
    page
      .getByRole("combobox", { name: "Sort samples", exact: true })
      .selectOption("filename"),
  );
  assert.equal(lastQuery.sort, "filename");
  assert.deepEqual(
    filenames.items.map((item) => item.filename),
    filenames.items.map((item) => item.filename).sort(),
  );
  const qualities = await queryAfter(() =>
    page
      .getByRole("combobox", { name: "Sort samples", exact: true })
      .selectOption("quality"),
  );
  assert.equal(lastQuery.sort, "quality");
  assert.deepEqual(
    qualities.items.map((item) => item.quality_score),
    qualities.items.map((item) => item.quality_score).sort((a, b) => a - b),
  );
  checks.push(
    "Evidence fits six complete samples at 1440 × 900 in both languages, every block is at most 120px, and server review/filename/quality sorting remains correct across pagination",
  );
  const example = await queryAfter(() =>
    page
      .getByRole("button", { name: "Find pedestrian annotation gaps" })
      .click(),
  );
  assert.equal(example.total, 47);
  assert.ok(
    example.items.every(
      (item) => item.split === "val" && item.near_duplicates.length,
    ),
  );
  const table = page.getByRole("table", { name: "Evidence results" });
  const fixedFilename = "val/scene-0817/image.png";
  let selectedPage = example;
  let first = selectedPage.items.find(
    (item) => item.filename === fixedFilename,
  );
  let skippedPages = 0;
  while (!first && selectedPage.next_cursor) {
    selectedPage = await queryAfter(() =>
      page.getByRole("button", { name: "Next page", exact: true }).click(),
    );
    skippedPages++;
    first = selectedPage.items.find((item) => item.filename === fixedFilename);
  }
  assert.ok(
    first,
    "The fixed scene-0817 sample must belong to the 47 canonical annotation gaps",
  );
  const firstRow = table.locator("tbody tr").filter({
    has: page.getByRole("button", {
      name: `Inspect ${first.filename}`,
      exact: true,
    }),
  });
  await firstRow.waitFor();
  assert.equal(await firstRow.count(), 1);
  const image = firstRow.locator(".evidence-image > img");
  await image.scrollIntoViewIfNeeded();
  await image.evaluate((element) =>
    element.complete
      ? Promise.resolve()
      : new Promise((resolve, reject) => {
          element.addEventListener("load", resolve, { once: true });
          element.addEventListener("error", reject, { once: true });
        }),
  );
  assert.ok(
    await image.evaluate(
      (element) => element.naturalWidth > 0 && element.naturalHeight > 0,
    ),
  );
  assert.match(
    await image.getAttribute("src"),
    new RegExp(`version=${first.source_version}`),
  );
  assert.ok((await firstRow.locator("mark").count()) > 0);
  const sourceEntries = page.locator(".source-footnotes > li");
  const sourceIds = await sourceEntries.evaluateAll((elements) =>
    elements.map((element) => element.dataset.sourceId),
  );
  assert.equal(new Set(sourceIds).size, sourceIds.length);
  assert.ok(sourceIds.length > 0);
  assert.equal(await firstRow.locator(".evidence-version").count(), 0);
  assert.equal(
    await table.locator("caption code").textContent(),
    first.source_version,
  );
  assert.equal(await firstRow.getByText("100%", { exact: true }).count(), 0);
  const anchoredConcepts = first.assertions
    .filter((assertion) =>
      assertion.anchors.some((anchor) => anchor.selector?.type === "text_span"),
    )
    .map((assertion) => assertion.object?.concept);
  const linkedConcept = first.annotation_boxes.find((box) =>
    anchoredConcepts.includes(box.concept),
  )?.concept;
  assert.ok(
    linkedConcept,
    "The real sample links a caption concept to an annotation box",
  );
  await firstRow
    .getByRole("button", { name: `${linkedConcept} · Mentions`, exact: true })
    .hover();
  const linkedNumbers = [];
  for (const selector of [
    ".assertion-matrix tr",
    ".evidence-anchor",
    ".annotation-box",
  ]) {
    const element = firstRow
      .locator(`${selector}[data-anchor-id="${linkedConcept}"]`)
      .first();
    assert.match(await element.getAttribute("class"), /is-linked/);
    linkedNumbers.push(await element.getAttribute("data-anchor-number"));
  }
  assert.ok(
    linkedNumbers.every((number) => number && number === linkedNumbers[0]),
  );
  const beforeFootnote = new URL(page.url()).hash;
  const footnoteReference = firstRow.locator(".footnote-reference a").first();
  const footnoteTarget = (await footnoteReference.getAttribute("href")).slice(
    1,
  );
  await footnoteReference.click();
  assert.equal(new URL(page.url()).hash, beforeFootnote);
  assert.equal(
    await page.evaluate(
      () => globalThis.document.activeElement?.closest("li")?.id,
    ),
    footnoteTarget,
  );
  await firstRow.scrollIntoViewIfNeeded();
  const overlay = table.locator(".annotation-box").first();
  await overlay.scrollIntoViewIfNeeded();
  const bounds = await overlay.boundingBox();
  assert.ok(
    bounds.width > 0 && bounds.height > 0,
    "The real overlay must have nonzero dimensions",
  );
  for (const name of [
    "Create version",
    "Quarantine selection",
    "Delete selection",
  ])
    assert.equal(
      await page.getByRole("button", { name, exact: true }).isDisabled(),
      true,
    );
  await screenshot("evidence-filtered");
  await screenshot("evidence-page-viewport", false);
  checks.push(
    "47-item canonical val/person/annotation-gap/train-neighbor filter, versioned image, NFC highlights, nonzero overlay, sources, quality and three actions",
  );

  await firstRow.getByRole("checkbox").check();
  const nextAvailable = await page
    .getByRole("button", { name: "Next page", exact: true })
    .isEnabled();
  const away = nextAvailable ? "Next page" : "Previous page";
  const back = nextAvailable ? "Previous page" : "Next page";
  await queryAfter(() =>
    page.getByRole("button", { name: away, exact: true }).click(),
  );
  assert.equal(
    await page
      .getByRole("button", { name: "Create version", exact: true })
      .isDisabled(),
    true,
  );
  await queryAfter(() =>
    page.getByRole("button", { name: back, exact: true }).click(),
  );
  await firstRow.waitFor();
  const detailResponse = page.waitForResponse((response) =>
    response
      .url()
      .includes(
        `/api/evidence/assets/${first.asset_ref.asset_id}?version_id=${first.source_version}`,
      ),
  );
  await page
    .getByRole("button", { name: `Inspect ${first.filename}`, exact: true })
    .click();
  const original = await (await detailResponse).json();
  const mention = original.assertions.find(
    (item) =>
      item.predicate === "mentions" && item.object?.concept === "person",
  );
  assert.ok(mention, "The required caption assertion must be reviewable");
  const dialog = page.getByRole("dialog", { name: "Sample evidence details" });
  const card = dialog.getByRole("article", {
    name: `mentions: ${mention.id}`,
    exact: true,
  });
  await card.waitFor();
  const selectedAssertion = () =>
    dialog
      .locator(".assertion-review-card.is-active")
      .getAttribute("data-assertion-id");
  const initialAssertion = await selectedAssertion();
  await dialog.press("j");
  assert.notEqual(await selectedAssertion(), initialAssertion);
  await dialog.press("k");
  assert.equal(await selectedAssertion(), initialAssertion);
  await card.getByRole("button", { name: "Locate evidence" }).click();
  const mutationRequests = [];
  const observeMutation = (request) => {
    if (
      request.method() === "POST" &&
      !request.url().endsWith("/api/evidence/query")
    )
      mutationRequests.push(request.url());
  };
  page.on("request", observeMutation);
  await dialog.dispatchEvent("compositionstart", { data: "证" });
  for (const key of ["j", "k", "a", "r", "Escape", "Enter"])
    await dialog.press(key);
  assert.equal(await dialog.isVisible(), true);
  assert.equal(await selectedAssertion(), mention.id);
  await dialog.dispatchEvent("compositionend", { data: "证" });
  const nativeDefaults = await dialog.evaluate((element) =>
    ["j", "k", "a", "r", "Escape", "Enter"].map((key) => {
      const event = new globalThis.KeyboardEvent("keydown", {
        key,
        isComposing: true,
        bubbles: true,
        cancelable: true,
      });
      element.dispatchEvent(event);
      return { key, prevented: event.defaultPrevented };
    }),
  );
  assert.deepEqual(nativeDefaults, [
    { key: "j", prevented: false },
    { key: "k", prevented: false },
    { key: "a", prevented: false },
    { key: "r", prevented: false },
    { key: "Escape", prevented: true },
    { key: "Enter", prevented: true },
  ]);
  assert.equal(await selectedAssertion(), mention.id);
  assert.equal(await dialog.isVisible(), true);
  assert.deepEqual(mutationRequests, []);
  page.off("request", observeMutation);
  assert.equal(await page.locator(".source-footnotes").count(), 1);
  assert.ok((await dialog.locator("mark").count()) > 0);
  const reviewRuns = [];
  for (const [name, status, shortcut] of [
    ["Accept assertion", "accepted", "a"],
    ["Reject assertion", "rejected", "r"],
    ["Restore candidate", "candidate", null],
  ]) {
    const decided = page.waitForResponse(
      (response) =>
        response.url().endsWith("/api/evidence/assertions/decide") &&
        response.request().method() === "POST",
    );
    await card.getByRole("button", { name, exact: true }).waitFor();
    const refreshed = await queryAfter(() =>
      shortcut
        ? dialog.press(shortcut)
        : card.getByRole("button", { name, exact: true }).click(),
    );
    const run = await (await decided).json();
    assert.equal(run.status, "SUCCEEDED");
    reviewRuns.push(run.id);
    await dialog
      .locator(
        `.assertion-review-card.${status}[aria-label="mentions: ${mention.id}"]`,
      )
      .waitFor();
    if (status === "rejected")
      assert.ok(
        refreshed.items.every(
          (item) => item.asset_ref.asset_id !== first.asset_ref.asset_id,
        ),
      );
    const detail = await json(
      `/api/evidence/assets/${first.asset_ref.asset_id}?version_id=${first.source_version}`,
    );
    const changed = detail.assertions.find((item) => item.id === mention.id);
    assert.equal(changed.status, status);
    for (const key of [
      "subject",
      "object",
      "anchors",
      "extractor",
      "producer_event_id",
    ])
      assert.deepEqual(changed[key], mention[key]);
  }
  await screenshot("evidence-reviewed");
  await dialog.evaluate((element) => {
    element.scrollTop = 0;
  });
  await screenshot("evidence-drawer-viewport", false);
  await dialog.press("Escape");
  await dialog.waitFor({ state: "hidden" });
  checks.push(
    "source-version detail lookup, numbered hover links and one page-level source list; j/k/a/r/Esc work and both composition guards suppress every shortcut/Enter without mutations; exactly three real accept/reject/candidate runs preserve immutable evidence and rejected query exclusion",
  );

  const actionRuns = [];
  for (const name of ["Create version", "Quarantine selection"]) {
    await firstRow.getByRole("checkbox").check();
    const prepared = page.waitForResponse(
      (response) =>
        response.url().endsWith("/prepare") &&
        response.request().method() === "POST",
    );
    const executed = page.waitForResponse(
      (response) =>
        response.url().endsWith("/execute") &&
        response.request().method() === "POST",
    );
    await queryAfter(() =>
      page.getByRole("button", { name, exact: true }).click(),
    );
    const planResponse = await prepared;
    const body = planResponse.request().postDataJSON();
    assert.equal(body.selection.dataset_id, first.dataset_id);
    assert.deepEqual(body.selection.version_ids, [first.source_version]);
    assert.deepEqual(body.selection.filters[0].value, [
      first.asset_ref.asset_id,
    ]);
    const run = await (await executed).json();
    assert.equal(run.status, "SUCCEEDED");
    actionRuns.push(run.id);
    await page.getByRole("region", { name: "Receipt", exact: true }).waitFor();
    assert.equal(
      await page
        .getByRole("button", { name: "Approve and delete files" })
        .count(),
      0,
    );
    if (name === "Create version") {
      const versions = await json(`/api/datasets/${first.dataset_id}/versions`);
      assert.ok(
        versions.some(
          (version) =>
            version.file_count === 1 &&
            version.manifest?.some(
              (file) => file.id === first.asset_ref.asset_id,
            ),
        ),
      );
    }
    await screenshot(
      name === "Create version"
        ? "evidence-created-version"
        : "evidence-quarantined",
    );
  }
  await firstRow.getByRole("checkbox").check();
  const runsBefore = await json("/api/actions/runs");
  const pending = page.waitForResponse((response) =>
    response.url().endsWith("/api/actions/delete_files/prepare"),
  );
  await page
    .getByRole("button", { name: "Delete selection", exact: true })
    .click();
  const deletionPlan = await (await pending).json();
  await page
    .getByRole("button", { name: "Approve and delete files", exact: true })
    .waitFor();
  assert.equal((await json("/api/actions/runs")).length, runsBefore.length);
  assert.equal(deletionPlan.status, "PREPARED");
  await screenshot("evidence-delete-pending");
  checks.push(
    "exact checked version/IDs create a frozen version and quarantine automatically; delete remains PREPARED with zero execution",
  );

  await page
    .getByRole("button", { name: `Inspect ${first.filename}`, exact: true })
    .click();
  await dialog
    .getByRole("link", { name: "View evidence subgraph", exact: true })
    .click();
  await page
    .locator(".graph-edge.semantic")
    .first()
    .waitFor({ state: "attached" });
  await page
    .locator(".graph-edge.lineage")
    .first()
    .waitFor({ state: "attached" });
  await page.waitForURL((url) => url.hash.startsWith("#/object/file/"));
  const objectHash = new URL(page.url()).hash;
  assert.equal(
    objectHash.split("?")[0],
    `#/object/file/${encodeURIComponent(first.asset_ref.asset_id)}`,
  );
  const objectQuery = new URLSearchParams(objectHash.split("?")[1]);
  assert.equal(objectQuery.get("tab"), "relations");
  assert.equal(objectQuery.get("dataset"), first.dataset_id);
  await page
    .getByRole("article", { name: "Object archive", exact: true })
    .waitFor();
  assert.ok((await page.locator(".graph-node").count()) <= 25);
  for (const label of await page
    .locator(".archive-card-button")
    .allTextContents())
    assert.doesNotMatch(
      label,
      /[\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12}/i,
    );
  const actionGroup = page.getByRole("button", {
    name: "Inspect decide_assertions",
    exact: true,
  });
  await actionGroup.waitFor();
  const groupCount = Number(
    (await actionGroup.locator(".archive-multiple").textContent())
      .replace("×", "")
      .trim(),
  );
  assert.equal(groupCount, 3);
  assert.equal(reviewRuns.length, 3);
  await actionGroup.hover();
  const groupPreview = page.getByRole("tooltip");
  for (const runId of reviewRuns)
    assert.ok((await groupPreview.textContent()).includes(runId));
  await actionGroup.click();
  const members = page.getByRole("region", {
    name: `decide_assertions · ${groupCount} runs`,
    exact: true,
  });
  await members.waitFor();
  assert.equal(
    await members.getByRole("button", { name: /^Copy ID/ }).count(),
    groupCount,
  );
  assert.equal(
    await page.getByText("Semantic similarity", { exact: true }).isVisible(),
    true,
  );
  const styles = await page.locator(".graph-edge").evaluateAll((elements) =>
    elements.map((element) => ({
      kind: element.classList.contains("semantic")
        ? "semantic"
        : element.classList.contains("catalog")
          ? "catalog"
          : "lineage",
      stroke:
        element.ownerDocument.defaultView.getComputedStyle(element).stroke,
      dash: element.ownerDocument.defaultView.getComputedStyle(element)
        .strokeDasharray,
    })),
  );
  const semanticStyle = styles.find((item) => item.kind === "semantic");
  const lineageStyle = styles.find((item) => item.kind === "lineage");
  assert.ok(semanticStyle && lineageStyle);
  assert.notDeepEqual(
    [semanticStyle.stroke, semanticStyle.dash],
    [lineageStyle.stroke, lineageStyle.dash],
  );
  await screenshot("evidence-subgraph");
  checks.push(
    "evidence link resolves to the canonical file object relations tab; bounded archive graph preserves lineage/semantic styles and legend; merged decide_assertions exposes all three real review IDs and expands its members",
  );

  await queryAfter(() =>
    page
      .locator(".sidebar")
      .getByRole("link", { name: "Evidence", exact: true })
      .click(),
  );
  await queryAfter(() =>
    page
      .getByRole("button", { name: "Find pedestrian annotation gaps" })
      .click(),
  );
  await page.locator(".evidence-filter-panel > summary").click();
  const unknown = await queryAfter(() =>
    page
      .getByRole("combobox", { name: "Annotation gap", exact: true })
      .selectOption("unknown"),
  );
  assert.ok(unknown.total > 0);
  assert.ok((await table.locator(".tri-state.unknown").count()) > 0);
  await screenshot("evidence-unknown");
  await queryAfter(() =>
    page
      .getByRole("button", { name: "Find pedestrian annotation gaps" })
      .click(),
  );
  const filteredEmpty = await queryAfter(() =>
    page
      .getByRole("spinbutton", { name: "Maximum quality", exact: true })
      .fill("0"),
  );
  assert.equal(filteredEmpty.total, 0);
  await page.locator('.evidence-empty[data-empty-kind="filtered"]').waitFor();
  await screenshot("evidence-empty-filtered");
  const recovered = await queryAfter(() =>
    page
      .getByRole("button", { name: "Remove Maximum quality", exact: true })
      .click(),
  );
  assert.equal(recovered.total, 47);
  assert.equal(
    await page
      .getByRole("combobox", { name: "Caption concept", exact: true })
      .inputValue(),
    "person",
  );
  assert.equal(
    await page
      .getByRole("combobox", { name: "Annotation gap", exact: true })
      .inputValue(),
    "missing",
  );
  await queryAfter(() =>
    page.getByRole("button", { name: "Reset filters" }).click(),
  );
  const corrupt = await queryAfter(() =>
    page
      .getByRole("spinbutton", { name: "Maximum quality", exact: true })
      .fill("0"),
  );
  assert.equal(corrupt.total, 10);
  assert.equal(await table.locator(".evidence-image > img").count(), 0);
  assert.equal(
    await table
      .getByRole("img", { name: "Image unavailable", exact: true })
      .count(),
    10,
  );
  await screenshot("evidence-corrupt-placeholders");
  await page
    .getByRole("combobox", { name: "Language", exact: true })
    .selectOption("zh");
  await screenshot("evidence-zh");
  checks.push(
    "unknown remains visibly distinct; ten corrupt images use honest placeholders without failed requests; evidence labels translate to Chinese",
  );
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  const datasets = await json("/api/datasets");
  const legacy = datasets.find(
    (dataset) => !dataset.metadata.evidence_samples && dataset.file_count > 0,
  );
  assert.ok(legacy, "A real dataset without extraction must remain available");
  await queryAfter(() =>
    page
      .getByRole("combobox", { name: "Evidence dataset", exact: true })
      .selectOption(legacy.id),
  );
  await page.locator('.evidence-empty[data-empty-kind="extraction"]').waitFor();
  await page
    .getByText("Generate or import paired samples locally", { exact: true })
    .click();
  await page
    .getByText(
      "Evidence extraction requires paired images with caption or annotation references.",
      { exact: false },
    )
    .waitFor();
  assert.equal(
    await page
      .getByRole("button", { name: "Prepare evidence extraction", exact: true })
      .count(),
    0,
  );
  assert.ok(
    (await page.locator(".evidence-extraction code").textContent()).includes(
      "import_evidence_samples",
    ),
  );
  await screenshot("evidence-empty-extraction");
  const empty = await post("/api/datasets", {
    name: "Empty evidence smoke fixture",
    files: [],
    metadata: {},
  });
  assert.equal(empty.file_count, 0);
  await queryAfter(() => page.reload());
  const noData = await queryAfter(() =>
    page
      .getByRole("combobox", { name: "Evidence dataset", exact: true })
      .selectOption(empty.id),
  );
  assert.equal(noData.total, 0);
  await page.locator('.evidence-empty[data-empty-kind="data"]').waitFor();
  assert.equal(
    await page
      .getByRole("link", { name: "Open data library", exact: true })
      .getAttribute("href"),
    "#/datasets",
  );
  await screenshot("evidence-empty-data");
  checks.push(
    "Three genuine empty states have actionable entries: impossible filters remove one condition and recover 47 samples; unpaired legacy data explains required inputs and provides the real local paired importer; an API-created empty dataset links to the data library",
  );
  return {
    density,
    emptyDatasetId: empty.id,
    sample: first.asset_ref,
    reviewFilename: first.filename,
    protectedScene: first.asset_ref.asset_id,
    skippedReviewPages: skippedPages,
    sourceVersion: first.source_version,
    filteredTotal: example.total,
    overlayBounds: bounds,
    reviewRuns,
    actionRuns,
    pendingDeletionPlanId: deletionPlan.id,
  };
}
