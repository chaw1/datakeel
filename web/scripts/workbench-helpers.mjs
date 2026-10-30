import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

export function workbenchBase(value) {
  const base = new URL(value);
  assert.equal(base.protocol, "http:");
  assert.ok(["127.0.0.1", "localhost", "[::1]"].includes(base.hostname));
  assert.equal(base.port, "8840", "Workbench tests use only port 8840");
  assert.equal(base.username + base.password + base.search + base.hash, "");
  assert.equal(base.pathname, "/");
  return base;
}

export function percentile(values, quantile = 0.95) {
  assert.ok(values.length > 0);
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(sorted.length * quantile) - 1)];
}

export async function poll(read, predicate, description, timeout = 20_000) {
  const deadline = Date.now() + timeout;
  while (Date.now() < deadline) {
    const value = await read();
    if (predicate(value)) return value;
    await delay(50);
  }
  throw new Error(`Timed out: ${description}`);
}

/**
 * The "Selected annotation" list. A select's accessible name also carries its
 * chosen option, so match the label prefix instead of an exact name.
 */
export function selectedAnnotation(page) {
  return page.getByRole("combobox", { name: /^Selected annotation\b/ });
}

/** Move to the start of a textarea the way the platform does it. */
export const textStartKey =
  process.platform === "darwin" ? "Meta+ArrowUp" : "Control+Home";

/** Move focus using real Tab events; queries never inject focus or UI state. */
export async function tabTo(page, target) {
  await target.waitFor({ state: "visible" });
  for (let step = 0; step < 250; step += 1) {
    if (
      await target.evaluate(
        (node) => node === globalThis.document.activeElement,
      )
    )
      return;
    await page.keyboard.press("Tab");
  }
  throw new Error("Could not reach control with Tab");
}

export function createHarness(context, page, base, output, manifest, report) {
  const button = (name) => page.getByRole("button", { name, exact: true });
  async function api(endpoint, data) {
    const url = new URL(endpoint, base);
    assert.equal(url.origin, base.origin);
    assert.ok(url.pathname.startsWith("/api/"));
    const response =
      data === undefined
        ? await context.request.get(url.href, { maxRedirects: 0 })
        : await context.request.post(url.href, { data, maxRedirects: 0 });
    assert.ok(
      response.ok(),
      `${endpoint}: ${response.status()} ${await response.text()}`,
    );
    return response.json();
  }
  async function action(name, values) {
    const plan = await api(`/api/actions/${name}/prepare`, {
      request_id: randomUUID(),
      ...values,
    });
    assert.equal(plan.reversible, true, "Smoke actions must remain reversible");
    assert.equal(plan.external, false, "No external smoke actions");
    const run = await api(
      `/api/actions/${encodeURIComponent(plan.id)}/execute`,
      {
        actor: manifest.actor ?? "local",
        operation_id: plan.operation_id,
        plan_digest: plan.plan_digest,
      },
    );
    assert.equal(run.status, "SUCCEEDED", run.error ?? run.reason);
    return run.receipt?.quality?.details;
  }
  async function project(kind) {
    const fixture = manifest.projects[kind];
    assert.ok(fixture, `Missing generated ${kind} project`);
    return api(
      `/api/production/projects/${fixture.project_id}/workbench?limit=1000`,
    );
  }
  async function editableTask(kind, position = 0) {
    const data = await project(kind);
    const tasks = data.tasks.filter((task) =>
      ["pending", "in_progress"].includes(task.state),
    );
    assert.ok(
      tasks[position],
      `${kind} needs fresh editable task ${position}; regenerate fixtures`,
    );
    return tasks[position].id;
  }
  async function task(id) {
    return api(`/api/production/tasks/${id}/workbench`);
  }
  async function latest(id) {
    const detail = await task(id);
    const revision = detail.revisions.find(
      (item) => item.id === detail.task.latest_revision_id,
    );
    assert.ok(revision, `Expected a baseline revision for ${id}`);
    return revision;
  }
  async function waitTask(id, image = true) {
    await page.locator(`.wb-session[data-task-id="${id}"]`).waitFor();
    if (image && (await page.locator(".wb-image-editor").count())) {
      await page
        .locator(".wb-image-editor [role=status]")
        .waitFor({ state: "hidden" });
      assert.equal(
        await page.locator(".wb-image-editor [role=alert]").count(),
        0,
      );
      await page
        .getByRole("application", { name: "Annotation canvas", exact: true })
        .waitFor();
    }
  }
  async function open(kind, id, keyboard = false) {
    const fixture = manifest.projects[kind];
    await page.goto(
      `${base.origin}/#/labeling?project=${encodeURIComponent(fixture.project_id)}`,
    );
    await page.locator(".wb-task-table, .wb-session").first().waitFor();
    const back = button("Back to task list");
    if (await back.isVisible()) {
      if (keyboard) {
        await tabTo(page, back);
        await page.keyboard.press("Enter");
      } else await back.click();
    }
    const target = page.locator(`.wb-task-table button[data-task-id="${id}"]`);
    await target.waitFor();
    if (keyboard) {
      await tabTo(page, target);
      await page.keyboard.press("Enter");
    } else await target.click();
    await waitTask(id);
  }
  async function save() {
    await page.keyboard.press("Control+s");
    await page.locator('[data-save-state="saved"]').waitFor();
  }
  async function capture(name) {
    await page.screenshot({
      path: path.join(output, `${name}.png`),
      fullPage: true,
    });
    await writeFile(
      path.join(output, `${name}.txt`),
      await page.locator("body").innerText(),
    );
  }
  async function draft(id) {
    const projectId = (await task(id)).task.project_id;
    const key = `datakeel.annotation-draft:${manifest.actor ?? "local"}:${projectId}:${id}`;
    return page.evaluate((storageKey) => {
      const stored = globalThis.localStorage.getItem(storageKey);
      return stored ? JSON.parse(stored) : null;
    }, key);
  }
  return {
    context,
    page,
    base,
    output,
    manifest,
    report,
    button,
    api,
    action,
    project,
    editableTask,
    task,
    latest,
    waitTask,
    open,
    save,
    capture,
    draft,
  };
}
