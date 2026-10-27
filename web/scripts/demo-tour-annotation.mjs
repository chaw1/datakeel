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
  await panel
    .getByText("Reworked harbor annotations", { exact: true })
    .first()
    .waitFor();
  assert.match(await panel.innerText(), /Fleiss/);
  assert.match(await panel.innerText(), /κ|kappa/);
  await capture(
    "21-annotation-quality",
    "打开虚构港口数据集的标注质量，核对三人一致性、抽检历史与返工对比",
    { datasetId: dataset.id },
    panel,
  );
  report.annotationQuality = { datasetId: dataset.id, generated: true };
}
