import assert from "node:assert/strict";

export async function kgTour({ page, api, capture, report }) {
  await page.locator('.sidebar a[href="#/kg"]').click();
  await page.locator(".kg-relations tbody tr").first().waitFor();
  await page.getByLabel("查找实体", { exact: true }).fill("Vivo");
  const row = page
    .locator('.kg-relations tbody tr[data-verification="needs_review"]')
    .filter({ hasText: "Vivo" })
    .first();
  await row.waitFor();
  const id = await row.getAttribute("data-relation-id");
  await row.getByRole("button", { name: "查看关系证据", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "关系原文证据" });
  await dialog.locator(".kg-review-issues li").first().waitFor();
  assert.ok((await dialog.locator("mark").count()) > 0);
  assert.ok((await dialog.locator(".kg-missing").count()) > 0);
  await capture(
    "19-kg-source",
    "在知识图谱页查找 Vivo，查看原文与未核对的端点",
    { assertionId: id },
  );
  await dialog
    .getByRole("button", { name: "关闭图谱详情", exact: true })
    .click();
  await row.getByRole("checkbox").check();
  const response = page.waitForResponse(
    (item) =>
      item.url().endsWith("/api/evidence/assertions/decide") &&
      item.request().method() === "POST",
  );
  await page.getByRole("button", { name: "拒绝所选", exact: true }).click();
  const run = await (await response).json();
  assert.equal(run.status, "SUCCEEDED");
  await row.locator(".kg-badge.rejected").waitFor();
  await page.getByRole("tab", { name: "图视图", exact: true }).click();
  await page
    .locator(".kg-edge.rejected")
    .first()
    .waitFor({ state: "attached" });
  assert.equal(
    (await api(`/api/kg/relations/${id}`)).relation.assertion.status,
    "rejected",
  );
  await capture("20-kg-rejected", "拒绝所选待复核关系，在图中确认已拒绝边", {
    assertionId: id,
    decisionRunId: run.id,
  });
  report.knowledgeGraph = {
    assertionId: id,
    decisionRunId: run.id,
    state: "rejected",
  };
}
