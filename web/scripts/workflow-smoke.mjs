import assert from "node:assert/strict";
import { URLSearchParams } from "node:url";

export async function cleanupFixture(post) {
  return post("/api/datasets", {
    name: "Workflow cleanup demo",
    files: [
      { filename: "empty-a.txt", content_base64: "" },
      { filename: "empty-b.txt", content_base64: "" },
      {
        filename: "observation.txt",
        content_base64:
          "QSBnZW5lcmF0ZWQgb2JzZXJ2YXRpb24gd2l0aCBlbm91Z2ggdGV4dCB0byBiZSB1c2VmdWwu",
      },
    ],
    metadata: {
      description: "Three generated files reserved for workflow cleanup.",
    },
  });
}

export async function workflowJourney({
  page,
  base,
  dataset,
  json,
  capture,
  locale = "en",
}) {
  const labels =
    locale === "zh"
      ? {
          start: "运行工作流",
          review: "查看签批",
          approve: "签批并删除文件",
          back: "返回工作流",
          resume: "签批后继续",
        }
      : {
          start: "Run workflow",
          review: "Review approval",
          approve: "Approve and delete files",
          back: "Return to workflow",
          resume: "Continue after approval",
        };
  const existing = await json("/api/datasets");
  const original = existing.find(
    (item) => item.name === "Field notes · generated demo",
  );
  assert.ok(original);
  const originalCount = original.file_count;
  await page.goto(
    `${base.origin}/#/workflows?${new URLSearchParams({ workflow: "low-quality-cleanup", dataset: dataset.id })}`,
  );
  await page.locator(".workflow-card").first().waitFor();
  assert.equal(await page.locator(".workflow-card").count(), 3);
  assert.equal(
    await page.locator("#workflow-input-dataset_id").inputValue(),
    dataset.id,
  );
  assert.equal(
    await page.locator("#workflow-input-quality_max").inputValue(),
    "60",
  );
  const started = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        "/api/workflows/low-quality-cleanup/runs" &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: labels.start, exact: true }).click();
  const stream = await started;
  assert.equal(stream.status(), 200);
  assert.match(await stream.text(), /event: done/);
  const panel = page.locator('.workflow-run[data-run-status="PAUSED"]');
  await panel.waitFor();
  const runId = await panel.getAttribute("data-run-id");
  assert.ok(runId);
  const paused = await json(`/api/workflows/runs/${runId}`);
  assert.equal(paused.status, "PAUSED");
  const plan = await json(`/api/actions/plans/${paused.pending_plan_id}`);
  assert.equal(plan.impact.object_count, 2);
  assert.equal(plan.agent_id, "datakeel-workflow");
  assert.equal(plan.session_id, runId);
  const quarantined = await json(`/api/datasets/${dataset.id}/files`);
  assert.equal(quarantined.length, 3);
  assert.equal(
    quarantined.filter((file) => file.metadata.quarantined).length,
    2,
  );
  if (capture)
    await capture(
      "15-workflow-paused",
      "在独立三文件数据集上运行低质样本清理，自动隔离后暂停等待签批",
      { runId, planId: plan.id, selectedFiles: 2 },
      panel,
    );
  await panel.getByRole("link", { name: labels.review, exact: true }).click();
  const sheet = page.locator(`.approval-sheet[data-plan-id="${plan.id}"]`);
  await sheet.waitFor();
  assert.equal(
    await sheet.locator(`a[href="#/workflows?run=${runId}"]`).count(),
    1,
  );
  const executed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/actions/${plan.id}/execute`),
  );
  await sheet
    .getByRole("button", { name: labels.approve, exact: true })
    .click();
  assert.equal((await executed).status(), 200);
  await page.getByRole("link", { name: labels.back, exact: true }).click();
  await page.locator('.workflow-run[data-run-status="PAUSED"]').waitFor();
  assert.equal((await json(`/api/workflows/runs/${runId}`)).status, "PAUSED");
  const resumed = page.waitForResponse((response) =>
    response.url().endsWith(`/api/workflows/runs/${runId}/resume`),
  );
  await page.getByRole("button", { name: labels.resume, exact: true }).click();
  const resumedResponse = await resumed;
  assert.equal(resumedResponse.status(), 200);
  assert.match(await resumedResponse.text(), /event: done/);
  const completed = page.locator('.workflow-run[data-run-status="SUCCEEDED"]');
  await completed.waitFor();
  const files = await json(`/api/datasets/${dataset.id}/files`);
  assert.equal(files.length, 1);
  assert.equal(files[0].filename, "observation.txt");
  const actions = await json("/api/actions/runs");
  assert.equal(actions.filter((run) => run.plan_id === plan.id).length, 1);
  assert.equal(
    (await json(`/api/datasets/${original.id}`)).file_count,
    originalCount,
  );
  const finished = await json(`/api/workflows/runs/${runId}`);
  assert.equal(
    finished.steps.find((step) => step.id === "result").output.file_count,
    1,
  );
  if (capture)
    await capture(
      "16-workflow-complete",
      "签批后返回工作流并显式继续，复用删除回执并查看最终质量",
      { runId, remainingFiles: 1, deletionRuns: 1 },
      completed.locator('[data-step-id="result"]'),
    );
  await page.reload();
  await page.locator('.workflow-run[data-run-status="SUCCEEDED"]').waitFor();
  return {
    datasetId: dataset.id,
    runId,
    planId: plan.id,
    selectedFiles: 2,
    remainingFiles: 1,
    originalCount,
  };
}

export async function workflowRoutingSmoke({
  page,
  base,
  datasetId,
  json,
  capture,
}) {
  const before = await json("/api/workflows/runs");
  await page.goto(
    `${base.origin}/#/agent?dataset=${encodeURIComponent(datasetId)}`,
  );
  await page
    .getByRole("combobox", {
      name: "Dataset for a new conversation",
      exact: true,
    })
    .selectOption(datasetId);
  await page.getByText("Conversation budget", { exact: true }).first().click();
  await page
    .getByRole("spinbutton", { name: "Conversation token limit", exact: true })
    .fill("1000000");
  const created = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/agent/conversations") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  const conversation = await (await created).json();
  await page
    .locator(".conversation-list button.active")
    .filter({ hasText: conversation.id.slice(0, 8) })
    .waitFor();
  await page.locator(".message-composer textarea:enabled").waitFor();
  await page
    .getByRole("textbox", { name: "Message", exact: true })
    .fill("Run a dataset health check");
  const pending = page.waitForResponse(
    (response) =>
      response.url().endsWith("/messages") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Send message", exact: true }).click();
  const response = await pending;
  const stream = await response.text();
  assert.match(stream, /event: route/);
  assert.match(stream, /"model_routes":\[/);
  await page.locator(".model-routing").first().waitFor();
  const suggestion = page
    .getByRole("link", { name: "Run as workflow", exact: true })
    .last();
  await suggestion.waitFor();
  assert.equal((await json("/api/workflows/runs")).length, before.length);
  if (capture)
    await capture("agent-routing", {
      conversationId: conversation.id,
    });
  await suggestion.click();
  assert.equal(
    await page.locator("#workflow-input-dataset_id").inputValue(),
    datasetId,
  );
  assert.ok(new URL(page.url()).hash.includes("workflow=dataset-health"));
  assert.equal((await json("/api/workflows/runs")).length, before.length);
  return {
    conversationId: conversation.id,
    datasetId,
    suggestedWorkflow: "dataset-health",
    automaticallyStarted: false,
  };
}
