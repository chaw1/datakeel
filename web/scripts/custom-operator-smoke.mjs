import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { setTimeout as delay } from "node:timers/promises";
import { URLSearchParams } from "node:url";

// Only generated fixtures in the isolated loopback demo are written.
export async function customOperatorSmoke({
  page,
  json,
  post,
  screenshot,
  checks,
}) {
  const source = await readFile(
    new URL("../../examples/custom_operators/filter_lines.py", import.meta.url),
    "utf8",
  );
  const codeHash = createHash("sha256").update(source).digest("hex");
  const name = "smoke_filter";
  const fixture = await post("/api/datasets", {
    name: "Custom operator smoke fixture",
    files: [
      {
        filename: "lines.txt",
        content_base64: Buffer.from(
          "keep first\ndiscard second\nkeep third\n",
        ).toString("base64"),
      },
    ],
  });
  const language = page.getByRole("combobox", { name: /^(Language|语言)$/ });
  await language.selectOption("en");
  await page.locator('.sidebar a[href="#/custom-operators"]').click();
  await page
    .getByRole("textbox", { name: "Operator name", exact: true })
    .fill(name);
  await page
    .getByRole("textbox", { name: "Complete Python source", exact: true })
    .fill(source);
  await page
    .getByRole("combobox", { name: "Input modality", exact: true })
    .selectOption("text");
  const submitted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/custom-operators") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Submit for code review", exact: true })
    .click();
  const plan = await (await submitted).json();
  assert.equal(plan.action_type, "submit_custom_operator");
  assert.equal(plan.canonical_params.code, source);
  assert.equal(plan.canonical_params.code_hash, codeHash);
  assert.equal(plan.reversible, false);
  const sheet = page.locator(`[data-plan-id="${plan.id}"]`);
  await sheet.waitFor();
  assert.equal(
    await sheet.locator(".custom-source code").textContent(),
    source,
  );
  await sheet.getByText(codeHash, { exact: true }).waitFor();
  await sheet.scrollIntoViewIfNeeded();
  await screenshot("custom-operator-code-review-en", true);
  const executed = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/actions/${plan.id}/execute`) &&
      response.request().method() === "POST",
  );
  await sheet
    .getByRole("button", {
      name: "Approve and register custom operator code",
      exact: true,
    })
    .click();
  assert.equal((await (await executed).json()).status, "SUCCEEDED");
  const reference = `custom.${name}@${codeHash}`;
  const version = page.locator(`[data-custom-version="${reference}"]`);
  await version.waitFor();
  await version
    .getByRole("combobox", { name: `Dataset · ${name}`, exact: true })
    .selectOption(fixture.id);
  await version
    .getByRole("textbox", {
      name: `Parameters (JSON object) · ${name}`,
      exact: true,
    })
    .fill('{"contains":"keep"}');
  const scheduled = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/custom-operators/${codeHash}/runs`) &&
      response.request().method() === "POST",
  );
  await version
    .getByRole("button", { name: "Run in pipeline", exact: true })
    .click();
  const action = await (await scheduled).json();
  assert.equal(action.status, "QUEUED");
  let run;
  for (let attempt = 0; attempt < 120; attempt++) {
    run = (await json(`/api/custom-operators/runs?code_hash=${codeHash}`)).find(
      (item) => item.operator === reference,
    );
    if (run) break;
    await delay(250);
  }
  assert.ok(run, "The worker must record the sandbox attempt");
  assert.equal(run.success, true, JSON.stringify(run));
  assert.equal(run.backend, "container");
  assert.equal(run.output_count, 1);
  assert.ok(run.resources.wall_seconds > 0);
  assert.match(run.image_digest, /^sha256:[0-9a-f]{64}$/);
  assert.match(run.params_digest, /^[0-9a-f]{64}$/);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  const record = page.locator(`[data-custom-run="${run.id}"]`);
  await record.waitFor();
  await record.scrollIntoViewIfNeeded();
  await screenshot("custom-operator-run-en", false);
  const graph = await json(
    `/api/lineage/graph?${new URLSearchParams({ asset_id: fixture.id, max_nodes: "100" })}`,
  );
  const event = graph.events.find(
    (item) => item.quality?.custom_operator?.id === run.id,
  );
  assert.ok(
    event,
    "The sandbox attribution must be reachable from dataset lineage",
  );
  assert.equal(event.quality.custom_operator.code_hash, codeHash);
  assert.equal(event.quality.custom_operator.image_digest, run.image_digest);

  const editedSource =
    source + "\n# A changed source version requires another review.\n";
  const editedHash = createHash("sha256").update(editedSource).digest("hex");
  await page
    .getByRole("textbox", { name: "Complete Python source", exact: true })
    .fill(editedSource);
  const resubmitted = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/custom-operators") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Submit for code review", exact: true })
    .click();
  const editedPlan = await (await resubmitted).json();
  assert.notEqual(editedHash, codeHash);
  assert.equal(editedPlan.canonical_params.code_hash, editedHash);
  assert.equal(editedPlan.status, "PREPARED");
  const approved = await json("/api/custom-operators");
  assert.ok(approved.some((item) => item.id === reference));
  assert.equal(
    approved.some(
      (item) => item.name === name && item.code_hash === editedHash,
    ),
    false,
  );
  await language.selectOption("zh");
  await page
    .getByRole("heading", { name: "自定义算子", exact: true })
    .waitFor();
  await page
    .locator(`[data-plan-id="${editedPlan.id}"]`)
    .scrollIntoViewIfNeeded();
  await screenshot("custom-operator-code-review-zh", true);

  // Exercise the configuration warning UI without enabling unsafe execution.
  const configuration = await json("/api/custom-operators/configuration");
  const warningRoute = "**/api/custom-operators/configuration";
  await page.route(warningRoute, (route) =>
    route.fulfill({
      json: {
        ...configuration,
        backend: "subprocess",
        subprocess_enabled: true,
      },
    }),
  );
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await page.getByText("已启用不安全的开发执行后端", { exact: true }).waitFor();
  assert.equal(
    await version
      .getByRole("button", { name: "在算子链中运行", exact: true })
      .isDisabled(),
    true,
  );
  await page
    .getByText("已启用不安全的开发执行后端", { exact: true })
    .scrollIntoViewIfNeeded();
  await screenshot("custom-operator-unsafe-warning-zh", false);
  await language.selectOption("en");
  await page
    .getByText("Unsafe development backend enabled", { exact: true })
    .waitFor();
  await page
    .getByText("Unsafe development backend enabled", { exact: true })
    .scrollIntoViewIfNeeded();
  await screenshot("custom-operator-unsafe-warning-en", false);
  await page.unroute(warningRoute);
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await page
    .getByText("Unsafe development backend enabled", { exact: true })
    .waitFor({ state: "hidden" });
  checks.push(
    "custom operator real submission, complete code review, digest-bound approval, immutable registration, worker sandbox pipeline, run attribution and dataset lineage; changed code remains unapproved; bilingual unsafe-backend warning uses a synthetic disclosure without enabling subprocess execution",
  );
  return {
    datasetId: fixture.id,
    codeHash,
    editedHash,
    planId: plan.id,
    editedPlanId: editedPlan.id,
    runId: run.id,
    imageDigest: run.image_digest,
  };
}
