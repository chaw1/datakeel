import assert from "node:assert/strict";

import { poll, tabTo } from "./workbench-helpers.mjs";
import { addWithKeyboard } from "./workbench-keyboard.mjs";

async function localDraft(page, key) {
  return page.evaluate((storageKey) => {
    const value = globalThis.localStorage.getItem(storageKey);
    return value ? JSON.parse(value) : null;
  }, key);
}

async function remoteEdit(h, taskId, marker) {
  const before = await h.latest(taskId);
  const annotation = {
    ...before.annotation,
    attributes: { ...before.annotation.attributes, conflict_marker: marker },
  };
  await h.action("save_revision", {
    task_id: taskId,
    previous_revision_id: before.id,
    annotation,
    source: "human",
  });
  const after = await h.latest(taskId);
  assert.notEqual(after.id, before.id);
  return after;
}

async function conflict(h, taskId, marker) {
  const remote = await remoteEdit(h, taskId, marker);
  await addWithKeyboard(h, "box");
  await h.page.keyboard.press("Control+s");
  await h.page.locator('[data-save-state="conflict"]').waitFor();
  assert.equal(await h.button("Reload server revision").isVisible(), true);
  assert.equal(await h.button("Overwrite with my edits").isVisible(), true);
  const local = await h.draft(taskId);
  assert.ok(local?.annotation.boxes.length > remote.annotation.boxes.length);
  await h.page.waitForTimeout(1100);
  assert.equal(
    (await h.latest(taskId)).id,
    remote.id,
    "Conflict must not silently overwrite the remote head",
  );
  return { remote, local };
}

export async function durableEditing(h) {
  const taskId = await h.editableTask("box", 1);
  await h.open("box", taskId);
  await tabTo(
    h.page,
    h.page.getByRole("application", { name: "Annotation canvas", exact: true }),
  );
  const started = Date.now();
  const autoRequest = h.page.waitForRequest(
    (request) =>
      new URL(request.url()).pathname === "/api/actions/save_revision/prepare",
  );
  await h.page.keyboard.press("b");
  await autoRequest;
  const autoSaveDebounceMs = Date.now() - started;
  assert.ok(
    autoSaveDebounceMs <= 1000,
    `Automatic save started after ${autoSaveDebounceMs}ms`,
  );
  await h.page.locator('[data-save-state="saved"]').waitFor();
  const before = await h.latest(taskId);
  const projectId = h.manifest.projects.box.project_id;
  const key = `datakeel.annotation-draft:${h.manifest.actor ?? "local"}:${projectId}:${taskId}`;
  h.report.expectedFailurePhase = "W3-offline";
  await h.context.setOffline(true);
  await addWithKeyboard(h, "box");
  await h.page.locator('[data-save-state="offline"]').waitFor();
  const offline = await localDraft(h.page, key);
  assert.equal(
    offline.annotation.boxes.length,
    before.annotation.boxes.length + 1,
  );
  await h.page.waitForTimeout(1100);
  assert.deepEqual(
    (await localDraft(h.page, key)).annotation,
    offline.annotation,
  );

  // Keep data APIs unavailable while loading the shell from the local server.
  // This checks durable reload independently of browser offline-document caching.
  const outage = (route) => route.abort("internetdisconnected");
  await h.context.route("**/api/**", outage);
  await h.context.setOffline(false);
  await h.page.reload();
  await h.waitTask(taskId, false);
  assert.deepEqual(
    (await localDraft(h.page, key)).annotation,
    offline.annotation,
  );
  assert.equal(
    await h.page
      .getByLabel("Selected annotation", { exact: true })
      .locator("option")
      .count(),
    offline.annotation.boxes.length + 1,
  );
  await h.context.unroute("**/api/**", outage);
  await h.context.setOffline(true);
  await h.context.setOffline(false);
  await h.page.locator('[data-save-state="saved"]').waitFor();
  const recovered = await poll(
    () => h.latest(taskId),
    (revision) =>
      revision.annotation.boxes.length === offline.annotation.boxes.length,
    "automatic recovery save",
  );
  assert.equal(await localDraft(h.page, key), null);
  h.report.expectedFailurePhase = null;

  h.report.expectedFailurePhase = "W3-conflict";
  const first = await conflict(h, taskId, "reload-choice");
  await h.capture("W3-conflict");
  await h.button("Reload server revision").click();
  await h.page.locator('[data-save-state="saved"]').waitFor();
  assert.equal((await h.latest(taskId)).id, first.remote.id);
  assert.equal(await localDraft(h.page, key), null);
  const second = await conflict(h, taskId, "overwrite-choice");
  const submittedHeads = [];
  const request = (entry) => {
    if (new URL(entry.url()).pathname === "/api/actions/save_revision/prepare")
      submittedHeads.push(entry.postDataJSON().previous_revision_id);
  };
  h.page.on("request", request);
  await h.button("Overwrite with my edits").click();
  await h.page.locator('[data-save-state="saved"]').waitFor();
  h.page.off("request", request);
  const overwritten = await h.latest(taskId);
  assert.notEqual(overwritten.id, second.remote.id);
  assert.equal(
    submittedHeads.at(-1),
    second.remote.id,
    "Explicit overwrite must use a freshly read expected head",
  );
  assert.deepEqual(overwritten.annotation.boxes, second.local.annotation.boxes);
  assert.deepEqual(
    overwritten.annotation.attributes,
    second.local.annotation.attributes,
  );
  h.report.expectedFailurePhase = null;
  await h.capture("W3-recovered");
  return {
    taskId,
    autoSaveDebounceMs,
    offlineRevision: recovered.id,
    refreshFault: "API requests unavailable; local shell reachable",
    reloadChoice: first.remote.id,
    overwriteRevision: overwritten.id,
    expectedHead: submittedHeads.at(-1),
  };
}
