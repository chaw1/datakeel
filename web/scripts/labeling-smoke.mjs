import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";

/** Create one generated personal box project through public actions, then open a task. */
export async function labelingSmoke({ page, json, post, screenshot, checks }) {
  async function action(name, values) {
    const plan = await post(`/api/actions/${name}/prepare`, {
      request_id: randomUUID(),
      ...values,
    });
    assert.equal(plan.external, false, "No external smoke actions");
    if (!plan.reversible)
      await post(`/api/approvals/${plan.id}`, {
        approve: true,
        plan_digest: plan.plan_digest,
      });
    const run = await post(`/api/actions/${plan.id}/execute`, {
      plan_digest: plan.plan_digest,
    });
    assert.equal(run.status, "SUCCEEDED", `${name}: ${run.reason ?? ""}`);
    return run.receipt.quality.details;
  }
  const datasets = await json("/api/datasets");
  const source = datasets.find((item) => /^Aster harbor/.test(item.name));
  assert.ok(source, "The demo must include the generated harbor images");
  const [version] = await json(`/api/datasets/${source.id}/versions`);
  const labels = await action("create_label_set", {
    name: "Smoke harbor labels",
    labels: [
      { id: "boat", name: "Boat", shortcut: "1" },
      { id: "buoy", name: "Buoy", shortcut: "2" },
    ],
  });
  await action("publish_label_set", { label_set_id: labels.id, version: 1 });
  const project = await action("create_project", {
    name: "Smoke harbor boxes",
    dataset_id: source.id,
    version_id: version.id,
    label_set_id: labels.id,
  });
  await action("split_packages", { project_id: project.id, package_size: 10 });
  const workbench = await json(
    `/api/production/projects/${project.id}/workbench?limit=100`,
  );
  assert.equal(workbench.progress.total, version.file_count);
  const [first] = workbench.tasks;
  assert.ok(first, "The generated project must contain tasks");

  await page
    .getByRole("navigation", { name: "Main navigation", exact: true })
    .getByRole("link", { name: "Annotation workbench", exact: true })
    .click();
  await page.waitForURL(/#\/labeling/);
  await page
    .getByRole("combobox", { name: "Production project", exact: true })
    .selectOption(project.id);
  const firstName = workbench.task_samples.find(
    (item) => item.task_id === first.id,
  )?.name;
  assert.ok(firstName, "The task list must name each sample by file name");
  const open = page.getByRole("button", {
    name: `Open task ${firstName}`,
    exact: true,
  });
  await open.click();
  const session = page.locator(`.wb-session[data-task-id="${first.id}"]`);
  await session.waitFor();
  await session.locator(".wb-image-editor [role=status]").waitFor({
    state: "hidden",
  });
  assert.equal(
    await session.locator(".wb-image-editor [role=alert]").count(),
    0,
  );
  await session
    .getByRole("application", { name: "Annotation canvas", exact: true })
    .waitFor();
  const detail = await json(`/api/production/tasks/${first.id}/workbench`);
  assert.equal(detail.sample.id, first.sample_id);
  assert.equal(
    await session.locator("h2").first().textContent(),
    detail.sample.name,
  );
  await screenshot("labeling-task-open");
  await session
    .getByRole("button", { name: "Back to task list", exact: true })
    .click();
  await page.locator(".wb-task-table").waitFor();
  checks.push(
    "annotation workbench lists a project created through public actions and opens its first task with the image canvas ready",
  );
  return { projectId: project.id, taskId: first.id };
}
