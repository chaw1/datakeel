import assert from "node:assert/strict";

export async function imageKGSmoke({ page, json, post, screenshot, checks }) {
  await page
    .getByRole("combobox", { name: /^(Language|语言)$/ })
    .selectOption("en");
  await page.locator('.sidebar a[href="#/kg"]').click();
  const dataset = (await json("/api/datasets")).find(
    (item) => item.metadata.image_kg_samples === true,
  );
  assert.ok(dataset, "The image demo dataset must exist");
  await page
    .getByLabel("Graph dataset", { exact: true })
    .selectOption(dataset.id);
  await page.locator(".kg-relations tbody tr").first().waitFor();
  await page.getByLabel("Find an entity", { exact: true }).fill("");
  await page
    .getByLabel("Source verification", { exact: true })
    .selectOption("");
  const version = await page
    .getByLabel("Dataset version", { exact: true })
    .inputValue();
  const graph = await post("/api/kg/query", {
    dataset_id: dataset.id,
    version_id: version,
    limit: 500,
  });
  const located = graph.relations.find((item) => {
    const counts = {};
    for (const anchor of item.assertion.anchors)
      if (anchor.selector.type === "image_region")
        counts[anchor.asset_ref.asset_id] =
          (counts[anchor.asset_ref.asset_id] ?? 0) + 1;
    return (
      item.image_located &&
      item.assertion.predicate !== "kg.same_as" &&
      Object.values(counts).some((count) => count > 1)
    );
  });
  const unlocated = graph.relations.find(
    (item) => item.image_located === false,
  );
  assert.ok(
    located,
    "A diagram relation must retain multiple evidence regions",
  );
  assert.ok(
    unlocated,
    "A genuine recorded unlocated relation must remain visible",
  );
  for (const [kind, relation] of [
    ["located", located],
    ["unlocated", unlocated],
  ]) {
    const row = page.locator(
      `.kg-relations tbody tr[data-relation-id="${relation.assertion.id}"]`,
    );
    await row.getByRole("button", { name: "Inspect relation" }).click();
    const drawer = page.getByRole("dialog", {
      name: "Relation source evidence",
    });
    await drawer.locator(".kg-image img").first().waitFor();
    await drawer.locator(".kg-image img").evaluateAll(async (images) =>
      Promise.all(
        images.map(async (image) => {
          await image.decode();
          assertDimensions(image);
          function assertDimensions(value) {
            if (!value.naturalWidth)
              throw new Error("Original image failed to load");
          }
        }),
      ),
    );
    assert.ok(await drawer.locator(".kg-source-text mark").count());
    if (kind === "located")
      assert.ok((await drawer.locator(".kg-image-region").count()) > 1);
    else {
      assert.equal(await drawer.locator(".kg-image-region").count(), 0);
      await drawer
        .getByText("Not located on image; review required.")
        .first()
        .waitFor();
    }
    await screenshot(`image-kg-${kind}-en`, false);
    if (kind === "unlocated") {
      await drawer.getByRole("button", { name: "Close graph details" }).click();
      await page
        .getByRole("combobox", { name: "Language", exact: true })
        .selectOption("zh");
      await row.getByRole("button", { name: "查看关系证据" }).click();
      const chineseDrawer = page.getByRole("dialog", { name: "关系原文证据" });
      await chineseDrawer
        .getByText("图上未定位，需人工复核。")
        .first()
        .waitFor();
      await screenshot("image-kg-unlocated-zh", false);
      await chineseDrawer.getByRole("button", { name: "关闭图谱详情" }).click();
      await page
        .getByRole("combobox", { name: "语言", exact: true })
        .selectOption("en");
    } else
      await drawer.getByRole("button", { name: "Close graph details" }).click();
  }
  await page.getByRole("tab", { name: "Extraction runs", exact: true }).click();
  const failure = page
    .locator(".kg-report")
    .filter({ hasText: "scripted-transcription-truncated.png" });
  await failure.locator("summary").click();
  await failure.getByText("truncated", { exact: true }).first().waitFor();
  await screenshot("image-kg-transcription-failure", false);
  await page.locator(".kg-extraction > summary").click();
  await page
    .getByLabel("Extraction profile", { exact: true })
    .selectOption("replay-image-flash");
  await page
    .getByLabel("Image transcription profile", { exact: true })
    .selectOption("bailian-qwen35-flash");
  await page
    .getByRole("button", { name: "Prepare graph extraction", exact: true })
    .click();
  await page
    .getByRole("region", { name: "Image transcription estimate" })
    .waitFor();
  await page
    .getByText("Input estimated from the transcription output limit.")
    .waitFor();
  await screenshot("image-kg-external-consent", false);
  checks.push(
    "Image KG: original image multiple regions, transcript role highlights, genuine unlocated relation in English/Chinese, scripted truncation report, external vision consent without execution",
  );
  return {
    dataset_id: dataset.id,
    version_id: version,
    located: located.assertion.id,
    unlocated: unlocated.assertion.id,
  };
}
