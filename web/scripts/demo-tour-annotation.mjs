import assert from "node:assert/strict";

export async function annotationTour({ page, base, api, capture, report }) {
  const datasets = await api("/api/datasets");
  const dataset = datasets.find(
    (item) => item.metadata.annotation_qa_demo === true,
  );
  assert.ok(dataset, "The generated annotation dataset must exist");
  await page.goto(
    `${base.origin}/#/object/dataset/${encodeURIComponent(dataset.id)}?tab=annotation-quality`,
  );
  const panel = page.locator(".annotation-quality");
  await panel.waitFor();
  // Batch names live in <option> elements, which are never visible; read the selection of the
  // batch picker (the import form's rework-baseline picker lists the same batches).
  const batch = panel.getByRole("combobox", { name: /^标注批次/ });
  await batch.waitFor();
  assert.match(
    await batch.evaluate((element) => element.selectedOptions[0].text),
    /^Reworked harbor annotations/,
  );
  await panel.getByText("Fleiss").first().waitFor();
  const text = await panel.innerText();
  assert.match(text, /κ|kappa/);
  assert.match(text, /返工对比/);
  assert.match(text, /已修正问题\s*19\s/);
  assert.match(text, /新引入问题\s*1\s/);
  await capture(
    "21-annotation-quality",
    "打开虚构港口数据集的标注质量，核对三人一致性、抽检历史与返工对比",
    { datasetId: dataset.id },
    panel,
  );
  report.annotationQuality = { datasetId: dataset.id, generated: true };
}
