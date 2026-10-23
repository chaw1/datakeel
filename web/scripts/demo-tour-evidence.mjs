import assert from "node:assert/strict";

export async function evidenceTour({
  page,
  base,
  dataset,
  api,
  capture,
  report,
}) {
  async function queryAfter(change) {
    const pending = page.waitForResponse(
      (response) =>
        new URL(response.url()).pathname === "/api/evidence/query" &&
        response.request().method() === "POST",
    );
    await change();
    const response = await pending;
    assert.equal(response.status(), 200);
    const result = await response.json();
    await page
      .getByText(`${result.total} 个匹配样本`, { exact: true })
      .waitFor();
    return result;
  }
  await queryAfter(() => page.goto(`${base.origin}/#/evidence`));
  let result = await queryAfter(() =>
    page.getByRole("button", { name: "查找行人标注缺口", exact: true }).click(),
  );
  const filename = "val/scene-0817/image.png";
  let sample = result.items.find((item) => item.filename === filename);
  let pageNumber = 1;
  while (!sample && result.next_cursor) {
    result = await queryAfter(() =>
      page.getByRole("button", { name: "下一页", exact: true }).click(),
    );
    pageNumber++;
    sample = result.items.find((item) => item.filename === filename);
  }
  assert.ok(sample, "The canonical generated sample must be present");
  await page
    .getByRole("button", { name: `查看 ${filename}`, exact: true })
    .click();
  const detail = await api(
    `/api/evidence/assets/${sample.asset_ref.asset_id}?version_id=${sample.source_version}`,
  );
  const assertion = detail.assertions.find(
    (item) =>
      item.predicate === "mentions" && item.object?.concept === "person",
  );
  assert.ok(assertion);
  const dialog = page.getByRole("dialog", {
    name: "样本证据详情",
    exact: true,
  });
  await capture(
    "02a-evidence-overview",
    "打开 scene-0817，查看原图、caption、证据矩阵与断言来源",
    { filename, pageNumber },
  );
  const card = dialog.getByRole("article", {
    name: `mentions: ${assertion.id}`,
    exact: true,
  });
  await card.getByRole("button", { name: "定位证据", exact: true }).click();
  const decision = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/evidence/assertions/decide",
  );
  await card.getByRole("button", { name: "接受断言", exact: true }).click();
  const reviewRun = await (await decision).json();
  assert.equal(reviewRun.status, "SUCCEEDED");
  await dialog
    .locator(
      `.assertion-review-card.accepted[data-assertion-id="${assertion.id}"]`,
    )
    .waitFor();
  await capture(
    "02-evidence-review",
    "查找行人标注缺口，打开 scene-0817，定位并接受 mentions 断言",
    { filename, pageNumber, assertionId: assertion.id, runId: reviewRun.id },
  );
  await dialog.press("Escape");
  const row = page.locator(".evidence-sample-row").filter({
    has: page.getByRole("button", { name: `查看 ${filename}`, exact: true }),
  });
  await row.getByRole("checkbox").check();
  const versionExecution = page.waitForResponse(
    (response) =>
      response.url().endsWith("/execute") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "生成版本", exact: true }).click();
  const versionRun = await (await versionExecution).json();
  assert.equal(versionRun.status, "SUCCEEDED");
  const versions = await api(`/api/datasets/${dataset.id}/versions`);
  const version = versions.find(
    (item) =>
      item.file_count === 1 &&
      item.manifest?.some((file) => file.id === sample.asset_ref.asset_id),
  );
  assert.ok(version);
  await page.goto(`${base.origin}/#/object/dataset/${dataset.id}?tab=versions`);
  await page.locator(".object-body").waitFor();
  await capture(
    "03-created-version",
    "勾选已审样本，生成版本，再打开数据集的版本页",
    {
      versionId: version.id,
      fileCount: version.file_count,
      runId: versionRun.id,
    },
  );
  await page.goto(`${base.origin}/#/agent`);
  await page
    .getByRole("combobox", { name: "新会话的数据集", exact: true })
    .selectOption(dataset.id);
  await page.getByText("会话预算", { exact: true }).first().click();
  await page
    .getByRole("spinbutton", { name: "会话词元上限", exact: true })
    .fill("1000000");
  const created = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/agent/conversations" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "新建会话", exact: true }).click();
  const conversation = await (await created).json();
  assert.equal(conversation.config.provider, "fake");
  async function send(message) {
    await page
      .getByRole("textbox", { name: "消息", exact: true })
      .fill(message);
    const terminal = page.waitForResponse(
      (response) =>
        response.url().endsWith("/messages") &&
        response.request().method() === "POST",
    );
    await page.getByRole("button", { name: "发送消息", exact: true }).click();
    const response = await terminal;
    assert.equal(response.status(), 200);
    assert.match(await response.text(), /event: done/);
    await page.locator(".message-composer textarea:enabled").waitFor();
  }
  const query =
    "查找 val 中 caption 提到行人、没有行人标注并且与 train 近重复的证据样本";
  await send(query);
  const beforeRuns = await api("/api/actions/runs");
  await send("删除这些样本");
  const pending = await api("/api/approvals");
  const plan = pending.find(
    (item) =>
      item.session_id === conversation.id &&
      item.action_type === "delete_files",
  );
  assert.ok(plan && plan.impact.object_count > 0);
  assert.equal((await api("/api/actions/runs")).length, beforeRuns.length);
  await capture(
    "04-agent-proposal",
    "新建 fake 会话，查询证据后请求删除；确认只产生待签批计划",
    {
      conversationId: conversation.id,
      query,
      planId: plan.id,
      objectCount: plan.impact.object_count,
    },
  );
  await page.goto(`${base.origin}/#/approvals`);
  const sheet = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  await sheet.waitFor();
  await capture(
    "05-approval-sheet",
    "打开审批待办，核对受影响对象、不可逆提示与计划摘要",
    {
      planId: plan.id,
      digest: plan.plan_digest,
      objectCount: plan.impact.object_count,
    },
  );
  const execution = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${plan.id}/execute`),
  );
  await sheet
    .getByRole("button", { name: "签批并删除文件", exact: true })
    .click();
  const deletionRun = await (await execution).json();
  assert.equal(deletionRun.status, "SUCCEEDED");
  await page
    .getByRole("link", { name: "查看血缘回执", exact: true })
    .first()
    .click();
  await page.waitForURL(/tab=relations/);
  await page.locator(".graph-node").first().waitFor();
  await capture(
    "06-receipt-relations",
    "签批后打开血缘回执，追踪动作与受影响对象的关系",
    { runId: deletionRun.id, eventId: deletionRun.receipt.event_id },
  );
  report.evidence = {
    datasetId: dataset.id,
    sampleId: sample.asset_ref.asset_id,
    reviewedAssertionId: assertion.id,
    versionId: version.id,
    conversationId: conversation.id,
    deletionRunId: deletionRun.id,
  };
}
