import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

import { percentile, selectedAnnotation } from "./workbench-helpers.mjs";

export async function nextTaskLatency(h) {
  const data = await h.project("box");
  assert.ok(data.tasks.length >= 21, "W1 needs at least 20 next-task samples");
  const ordered = data.tasks.slice(0, 24).map((task) => task.id);
  const first = await h.task(ordered[0]);
  assert.equal(first.sample.image_width, 2000);
  assert.equal(first.sample.image_height, 1500);
  await h.open("box", ordered[0]);
  const samples = [];
  for (const taskId of ordered.slice(1)) {
    // Let the documented next-two prefetch settle before measuring a warm transition.
    await h.page.waitForLoadState("networkidle");
    const started = await h.page.evaluate(() => globalThis.performance.now());
    await h.page.keyboard.press("Alt+n");
    await h.page.waitForFunction(
      (id) => {
        const session = globalThis.document.querySelector(
          `.wb-session[data-task-id="${id}"]`,
        );
        return (
          session &&
          !session.querySelector(".wb-image-editor [role=status]") &&
          !session.querySelector(".wb-image-editor [role=alert]") &&
          session.querySelector("canvas") &&
          session.querySelectorAll("select option").length > 3
        );
      },
      taskId,
      { polling: "raf" },
    );
    // A second RAF includes the paint of the loaded image and existing annotation layer.
    await h.page.evaluate(
      () =>
        new Promise((resolve) =>
          globalThis.requestAnimationFrame(() =>
            globalThis.requestAnimationFrame(resolve),
          ),
        ),
    );
    const elapsed = await h.page.evaluate(
      (start) => globalThis.performance.now() - start,
      started,
    );
    assert.ok(
      (await selectedAnnotation(h.page).locator("option").count()) > 1,
      "Existing annotations must be visible",
    );
    samples.push({ taskId, milliseconds: elapsed });
  }
  const p95 = percentile(samples.map((sample) => sample.milliseconds));
  assert.ok(p95 <= 300, `Next-task p95 ${p95.toFixed(2)}ms exceeds 300ms`);
  return {
    image: [2000, 1500],
    samples,
    p95,
    limit: 300,
    preparation:
      "next-two prefetch settled before each measured keyboard transition; double RAF includes paint",
  };
}

async function panFrames(h) {
  const canvas = h.page.getByRole("application", {
    name: "Annotation canvas",
    exact: true,
  });
  await canvas.focus();
  await h.page.keyboard.press("+");
  await h.button("Pan image").click();
  const before = await canvas
    .locator("canvas")
    .first()
    .evaluate((node) => node.toDataURL());
  const bounds = await canvas.boundingBox();
  assert.ok(bounds);
  const cx = bounds.x + bounds.width / 2,
    cy = bounds.y + bounds.height / 2;
  await h.page.mouse.move(cx, cy);
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
          else resolve({ frames, duration: now - start });
        }
        globalThis.requestAnimationFrame(frame);
      }),
  );
  const started = Date.now();
  let moves = 0;
  while (Date.now() - started < 5100) {
    const progress = (Date.now() - started) / 1000;
    await h.page.mouse.move(
      cx + Math.sin(progress * 3) * 100,
      cy + Math.cos(progress * 2) * 70,
    );
    moves += 1;
    await delay(8);
  }
  await h.page.mouse.up();
  const after = await canvas
    .locator("canvas")
    .first()
    .evaluate((node) => node.toDataURL());
  assert.notEqual(
    after,
    before,
    "Scripted drag must actually move the rendered image",
  );
  const result = await measurement;
  assert.ok(
    result.frames.length >= 100,
    "Five-second pan must collect meaningful frame samples",
  );
  const p95 = percentile(result.frames.slice(1));
  assert.ok(p95 <= 33, `Pan frame p95 ${p95.toFixed(2)}ms exceeds 33ms`);
  return {
    duration: result.duration,
    samples: result.frames.length,
    moves,
    p95,
    limit: 33,
    frames: result.frames,
  };
}

export async function largeImages(h) {
  const checks = [];
  for (const [kind, width, height] of [
    ["large4k", 3840, 2160],
    ["large8k", 8000, 6000],
  ]) {
    const taskId = h.manifest.projects[kind].task_ids[0];
    const task = await h.task(taskId);
    assert.equal(task.sample.image_width, width);
    assert.equal(task.sample.image_height, height);
    assert.ok(
      task.sample.thumbnail_url,
      "Large images need a thumbnail-first source",
    );
    await h.open(kind, taskId);
    const baseline = (await h.latest(taskId)).annotation;
    const measurement = await panFrames(h);
    assert.deepEqual(
      (await h.latest(taskId)).annotation,
      baseline,
      "Panning must not alter annotations",
    );
    await h.capture(`W5-${kind}`);
    checks.push({
      kind,
      taskId,
      image: [width, height],
      thumbnail: task.sample.thumbnail_url,
      ...measurement,
    });
  }
  return checks;
}
