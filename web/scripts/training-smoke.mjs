import assert from "node:assert/strict";
import { Buffer } from "node:buffer";

import { mobileWidth, typographySample } from "./polish-smoke.mjs";
import { appearance, settle } from "./screenshots-helpers.mjs";

export function trainingFixture() {
  const question =
    "Why does the fictional silver observatory keep a separate written weather log beside its northern telescope during every evening shift?";
  const clean = {
    messages: [
      {
        role: "user",
        content: "Describe a quiet fictional harbor at sunrise.",
      },
      {
        role: "assistant",
        content:
          "A small wooden boat rests beside an empty pier while pale sunlight reaches the water.",
      },
    ],
  };
  const records = [
    clean,
    {
      instruction:
        "Where can the fictional reviewer receive the generated report?",
      input: "",
      output: "Send the generated report to reviewer@example.test for review.",
    },
    clean,
    {
      prompt: "Choose a concise greeting for the visitor.",
      chosen: "Welcome to the garden.",
      rejected: "Welcome to the garden.",
    },
    {
      messages: [
        { role: "user", content: question },
        {
          role: "assistant",
          content:
            "The independent log helps the fictional observers compare conditions across shifts.",
        },
      ],
    },
    {
      instruction: "解释这个 fictional coastal garden 的日常照料安排。",
      input: "请说明浇水、修剪和观察的时间。",
      output:
        "Garden care begins with watering before sunrise，接着修剪枝条，傍晚记录植物变化。",
    },
  ];
  const source =
    records.map((record) => JSON.stringify(record)).join("\n") +
    "\n{broken json\n";
  return {
    name: "Generated training governance demo",
    files: [
      {
        filename: "training.jsonl",
        content_base64: Buffer.from(source).toString("base64"),
      },
      {
        filename: "evaluation.txt",
        content_base64: Buffer.from(question + "\n").toString("base64"),
      },
    ],
  };
}

export async function trainingJourney({ page, base, json, create, capture }) {
  const dataset = await create(trainingFixture());
  const prefix = `/api/datasets/${encodeURIComponent(dataset.id)}`;
  const initialVersions = await json(`${prefix}/versions`);
  assert.equal(initialVersions.length, 1);
  const origin = new URL(base).origin;
  await page.goto(
    `${origin}/#/object/dataset/${encodeURIComponent(dataset.id)}?tab=text-governance`,
  );
  await appearance(page, "en", "light");
  const panel = page.locator(".training-governance");
  await panel.locator(".training-controls").waitFor();
  await panel
    .getByText("Register your evaluation set", { exact: true })
    .click();
  await panel
    .getByLabel("Evaluation set name", { exact: true })
    .fill("Generated observatory questions");
  await panel
    .getByRole("checkbox", { name: "evaluation.txt", exact: true })
    .check();
  const registration = page.waitForResponse(
    (response) =>
      response.url().endsWith(`${prefix}/text-governance/evaluations`) &&
      response.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Register evaluation set", exact: true })
    .click();
  const evaluation = await (await registration).json();
  await panel
    .getByRole("checkbox", { name: evaluation.name, exact: true })
    .waitFor();
  assert.equal(
    await panel
      .getByRole("checkbox", { name: evaluation.name, exact: true })
      .isChecked(),
    true,
  );
  const analysis = page.waitForResponse(
    (response) =>
      response.url().endsWith(`${prefix}/text-governance/analyze`) &&
      response.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Analyze and preview cleaning", exact: true })
    .click();
  const run = await (await analysis).json();
  assert.equal(run.report.records, 7);
  assert.ok(run.report.issue_counts.pii_email > 0);
  assert.ok(run.report.issue_counts.contamination > 0);
  assert.ok(run.report.issue_counts.exact_duplicate > 0);
  assert.ok(run.report.issue_counts.preference_identical > 0);
  await panel.locator(".training-preview mark").first().waitFor();
  assert.doesNotMatch(await panel.innerText(), /reviewer@example\.test/);
  assert.equal(
    (await json(`${prefix}/versions`)).length,
    1,
    "Dry run publishes no version",
  );
  const typography = [];
  for (const locale of ["en", "zh"]) {
    for (const theme of ["light", "dark"]) {
      await appearance(page, locale, theme);
      await settle(page);
      typography.push(
        await typographySample(page, `training-${locale}-${theme}`),
      );
      if (capture) await capture(`training-${locale}-${theme}`, panel);
    }
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await settle(page);
  const mobile = await mobileWidth(page, "training-governance");
  await page.setViewportSize({ width: 1440, height: 900 });
  await appearance(page, "en", "light");
  const preparing = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/training-governance/${run.id}/clean`) &&
      response.request().method() === "POST",
  );
  await panel
    .getByRole("button", { name: "Review cleaning plan", exact: true })
    .click();
  const plan = await (await preparing).json();
  assert.equal(plan.action_type, "clean_training_data");
  assert.equal(plan.reversible, false);
  assert.equal(
    (await json(`${prefix}/versions`)).length,
    1,
    "Preparation publishes no version",
  );
  const execution = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/api/actions/${plan.id}/execute`) &&
      response.request().method() === "POST",
  );
  await panel
    .getByRole("button", {
      name: "Approve and create a cleaned training version",
      exact: true,
    })
    .click();
  assert.equal((await execution).status(), 200);
  await panel
    .getByRole("link", { name: "View lineage receipt", exact: true })
    .waitFor();
  const versions = await json(`${prefix}/versions`);
  assert.equal(versions.length, 2);
  const saved = await json(`/api/training-governance/${run.id}`);
  assert.ok(saved.cleaned_version_id);
  assert.ok(versions.some((version) => version.id === initialVersions[0].id));
  return {
    datasetId: dataset.id,
    evaluationId: evaluation.id,
    runId: run.id,
    cleanedVersionId: saved.cleaned_version_id,
    records: run.report.records,
    issueCounts: run.report.issue_counts,
    typography,
    mobile,
  };
}
