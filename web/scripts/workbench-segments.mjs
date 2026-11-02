import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

import { percentile, poll, tabTo } from "./workbench-helpers.mjs";

const addName = "Add 1000ms segment (T)";

async function rangeChecks(h, taskId) {
  const detail = await h.task(taskId);
  const url = new URL(detail.sample.content_url, h.base).href;
  const results = [];
  for (const range of ["bytes=0-99", "bytes=100-199"]) {
    const response = await h.context.request.get(url, {
      headers: { Range: range, "X-Datakeel-Actor": h.manifest.actor },
    });
    assert.equal(response.status(), 206);
    const contentRange = response.headers()["content-range"];
    assert.match(contentRange, /^bytes (?:0|100)-(?:99|199)\/\d+$/);
    assert.equal((await response.body()).length, 100);
    assert.equal(response.headers()["accept-ranges"], "bytes");
    assert.ok(!JSON.stringify(response.headers()).includes(h.output));
    results.push({ range, status: response.status(), contentRange });
  }
  for (const range of ["bytes=999999999999-", "bytes=abc", "bytes=100-50"]) {
    const invalid = await h.context.request.get(url, {
      headers: { Range: range, "X-Datakeel-Actor": h.manifest.actor },
    });
    assert.ok([400, 416].includes(invalid.status()));
    results.push({ range, status: invalid.status() });
  }
  return results;
}

async function keyboardSegment(h, note) {
  const add = h.button(addName);
  await tabTo(h.page, add);
  await h.page.keyboard.press("t");
  const side = h.page.getByRole("textbox", { name: /^Side/ });
  await tabTo(h.page, side);
  await h.page.keyboard.type(note);
  await tabTo(h.page, add);
  await h.page.keyboard.press("2");
}

async function mouseWorkflow(h) {
  const taskId = await h.editableTask("segment", 0);
  const before = await h.latest(taskId);
  await h.open("segment", taskId);
  const timeline = h.page.getByRole("group", { name: /Segment timeline/ });
  const bounds = await timeline.boundingBox();
  assert.ok(bounds);
  const y = bounds.y + 15;
  await h.page.mouse.move(bounds.x + bounds.width * 0.8, y);
  await h.page.mouse.down();
  await h.page.mouse.move(bounds.x + bounds.width * 0.2, y, { steps: 8 });
  await h.page.mouse.up();
  await h.page.getByRole("textbox", { name: /^Side/ }).fill("鼠标");
  await h.save();
  const created = await h.latest(taskId);
  assert.equal(
    created.annotation.segments.length,
    before.annotation.segments.length + 1,
  );
  const body = h.page.locator(
    '.wb-segment-block[data-selected="true"] .wb-segment-body',
  );
  const bodyBounds = await body.boundingBox();
  assert.ok(bodyBounds);
  await h.page.mouse.move(
    bodyBounds.x + bodyBounds.width / 2,
    bodyBounds.y + 10,
  );
  await h.page.mouse.down();
  await h.page.mouse.move(
    bodyBounds.x + bodyBounds.width / 2 + 30,
    bodyBounds.y + 10,
    {
      steps: 4,
    },
  );
  await h.page.mouse.up();
  await h.save();
  const moved = await h.latest(taskId);
  assert.notEqual(moved.id, created.id);
  assert.equal(
    moved.annotation.segments.length,
    created.annotation.segments.length,
  );
  return {
    taskId,
    pointerCreates: 1,
    pointerMoves: 1,
    recordSegments: moved.annotation.segments.length,
  };
}

async function keyboardWorkflow(h) {
  const taskId = await h.editableTask("segment", 1);
  await h.open("segment", taskId, true);
  const before = await h.latest(taskId);
  for (const note of ["一", "二", "三"]) await keyboardSegment(h, note);
  await h.save();
  const saved = await h.latest(taskId);
  assert.equal(
    saved.annotation.segments.length,
    before.annotation.segments.length + 3,
  );
  assert.ok(
    saved.annotation.segments
      .slice(-3)
      .every((item) => item.category === "dog"),
  );
  await tabTo(h.page, h.button("Mark complete"));
  await h.page.keyboard.press("Control+Enter");
  const submitted = await poll(
    () => h.task(taskId),
    (value) => value.task.state === "approved",
    "segment keyboard submission",
  );
  assert.equal(submitted.task.approved_revision_id, saved.id);
  await h.open("segment", taskId);
  assert.equal(await h.button(addName).isDisabled(), true);
  const revisions = (await h.task(taskId)).revisions.length;
  await h.page.keyboard.press(".");
  await h.page.keyboard.press("+");
  assert.equal((await h.task(taskId)).revisions.length, revisions);
  return { taskId, created: 3, submitted: true, readOnlyPlayback: true };
}

async function offlineWorkflow(h) {
  const taskId = await h.editableTask("segment", 2);
  await h.open("segment", taskId);
  const before = await h.latest(taskId);
  await keyboardSegment(h, "离线");
  h.report.expectedFailurePhase = "W6-segment-offline";
  await h.context.setOffline(true);
  await h.page.locator('[data-save-state="offline"]').waitFor();
  const offline = await h.draft(taskId);
  assert.equal(
    offline.annotation.segments.length,
    before.annotation.segments.length + 1,
  );
  await h.context.setOffline(false);
  await h.page.reload();
  await h.waitTask(taskId, false);
  assert.equal(
    (await h.draft(taskId)).annotation.segments.length,
    offline.annotation.segments.length,
  );
  await h.page.locator('[data-save-state="saved"]').waitFor();
  const recovered = await h.latest(taskId);
  assert.equal(
    recovered.annotation.segments.length,
    offline.annotation.segments.length,
  );
  h.report.expectedFailurePhase = null;
  return {
    taskId,
    offlineSegments: offline.annotation.segments.length,
    recovered: true,
  };
}

async function transitionPerformance(h) {
  const data = await h.project("segment");
  const ids = data.tasks.map((task) => task.id);
  await h.open("segment", ids[0]);
  const samples = [];
  for (const taskId of ids.slice(1)) {
    await h.page.waitForLoadState("networkidle");
    const started = await h.page.evaluate(() => globalThis.performance.now());
    await h.page.keyboard.press("Alt+n");
    await h.page.waitForFunction(
      (id) => {
        const session = globalThis.document.querySelector(
          `.wb-session[data-task-id="${id}"]`,
        );
        const media = session?.querySelector("audio,video");
        return media && media.readyState >= 1;
      },
      taskId,
      { polling: "raf" },
    );
    samples.push(
      await h.page.evaluate(
        (start) => globalThis.performance.now() - start,
        started,
      ),
    );
  }
  const p95 = percentile(samples);
  assert.ok(
    p95 <= 300,
    `Segment next-task/playable p95 ${p95.toFixed(2)}ms exceeds 300ms`,
  );
  return { samples, p95, limit: 300, waitsForWholeMedia: false };
}

async function longPerformance(h) {
  const taskId = h.manifest.projects["segment-long"].task_ids[0];
  await h.open("segment-long", taskId);
  const baseline = await h.latest(taskId);
  assert.equal(baseline.annotation.segments.length, 500);
  await tabTo(h.page, h.button(addName));
  for (let index = 0; index < 6; index += 1) await h.page.keyboard.press("+");
  const pan = h.page.getByRole("slider", {
    name: "Visible timeline start (milliseconds)",
  });
  const panBounds = await pan.boundingBox();
  assert.ok(panBounds);
  await h.page.mouse.click(panBounds.x + panBounds.width / 2, panBounds.y + 3);
  await h.page.waitForTimeout(100);
  const visible = await h.page.locator(".wb-segment-body").count();
  assert.ok(
    visible > 0 && visible < 20,
    `Only the visible window renders, got ${visible}`,
  );
  assert.equal(await h.page.locator(".wb-attribute-fields").count(), 1);
  const body = h.page.locator(".wb-segment-body").first();
  const bounds = await body.boundingBox();
  assert.ok(bounds);
  const x = bounds.x + Math.max(4, bounds.width / 2),
    y = bounds.y + 10;
  await h.page.mouse.move(x, y);
  await h.page.mouse.down();
  const measurement = h.page.evaluate(
    () =>
      new Promise((resolve) => {
        const frames = [];
        const start = globalThis.performance.now();
        let previous = start;
        function frame(now) {
          frames.push(now - previous);
          previous = now;
          if (now - start < 5000) globalThis.requestAnimationFrame(frame);
          else resolve(frames.slice(1));
        }
        globalThis.requestAnimationFrame(frame);
      }),
  );
  const started = Date.now();
  while (Date.now() - started < 5100) {
    const progress = (Date.now() - started) / 1000;
    await h.page.mouse.move(x + Math.sin(progress * 3) * 30, y);
    await delay(8);
  }
  await h.page.mouse.up();
  const frames = await measurement;
  const p95 = percentile(frames);
  assert.ok(
    p95 <= 33,
    `500-segment drag frame p95 ${p95.toFixed(2)}ms exceeds 33ms`,
  );
  await h.save();
  assert.equal((await h.latest(taskId)).annotation.segments.length, 500);
  return {
    taskId,
    durationMs: 7_200_000,
    segments: 500,
    visible,
    frameSamples: frames.length,
    p95,
    limit: 33,
  };
}

async function videoPlayback(h) {
  const taskId = h.manifest.projects["segment-video"].task_ids[0];
  const revisions = (await h.task(taskId)).revisions.length;
  const started = await h.page.evaluate(() => globalThis.performance.now());
  await h.open("segment-video", taskId);
  const video = h.page.locator("video");
  await video.waitFor();
  await h.page.waitForFunction(() => {
    const media = globalThis.document.querySelector("video");
    return media && media.readyState >= 1;
  });
  const firstPlayable = await h.page.evaluate(
    (start) => globalThis.performance.now() - start,
    started,
  );
  assert.ok(
    firstPlayable <= 1000,
    `First playable ${firstPlayable.toFixed(2)}ms exceeds 1s`,
  );
  assert.equal(await video.getAttribute("preload"), "metadata");
  const seeks = [];
  for (const target of [1, 3, 2, 8, 5, 11, 4, 9]) {
    const elapsed = await video.evaluate(
      (media, seconds) =>
        new Promise((resolve) => {
          const start = globalThis.performance.now();
          media.addEventListener(
            "seeked",
            () => resolve(globalThis.performance.now() - start),
            { once: true },
          );
          media.currentTime = seconds;
        }),
      target,
    );
    seeks.push(elapsed);
  }
  await video.evaluate((media) => media.play());
  await h.page.waitForFunction(() => {
    const media = globalThis.document.querySelector("video");
    return media && !media.paused;
  });
  await video.evaluate((media) => media.pause());
  const seekP95 = percentile(seeks);
  assert.ok(
    seekP95 <= 300,
    `Loaded seek p95 ${seekP95.toFixed(2)}ms exceeds 300ms`,
  );
  assert.equal((await h.task(taskId)).revisions.length, revisions);
  return {
    taskId,
    firstPlayable,
    seekSamples: seeks,
    seekP95,
    revisionsChanged: 0,
  };
}

export async function segmentAcceptance(h) {
  const taskId = h.manifest.projects.segment.task_ids[0];
  const range = await rangeChecks(h, taskId);
  return {
    range,
    mouse: await mouseWorkflow(h),
    keyboard: await keyboardWorkflow(h),
    offline: await offlineWorkflow(h),
  };
}

export async function segmentPerformance(h) {
  return {
    video: await videoPlayback(h),
    transitions: await transitionPerformance(h),
    longMedia: await longPerformance(h),
  };
}
