import assert from "node:assert/strict";
import { setTimeout as delay } from "node:timers/promises";

import { percentile, selectedAnnotation } from "./workbench-helpers.mjs";

export async function nextTaskLatency(h, kind = "box") {
  const data = await h.project(kind);
  assert.ok(data.tasks.length >= 21, "W1 needs at least 20 next-task samples");
  const ordered = data.tasks.slice(0, 24).map((task) => task.id);
  const first = await h.task(ordered[0]);
  assert.equal(first.sample.image_width, 2000);
  assert.equal(first.sample.image_height, 1500);
  await h.open(kind, ordered[0]);
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
    const optionCount =
      kind === "keypoints"
        ? await h.page
            .getByRole("combobox", { name: "Skeleton instance", exact: true })
            .locator("option")
            .count()
        : await selectedAnnotation(h.page).locator("option").count();
    assert.ok(optionCount > 1, "Existing annotations must be visible");
    samples.push({ taskId, milliseconds: elapsed });
  }
  const p95 = percentile(samples.map((sample) => sample.milliseconds));
  assert.ok(p95 <= 300, `Next-task p95 ${p95.toFixed(2)}ms exceeds 300ms`);
  return {
    kind,
    image: [2000, 1500],
    samples,
    p95,
    limit: 300,
    preparation:
      "next-two prefetch settled before each measured keyboard transition; double RAF includes paint",
  };
}

async function panFrames(h, keypoints = false) {
  const canvas = keypoints
    ? h.page
        .getByRole("region", { name: "Skeleton keypoints", exact: true })
        .getByRole("application", { name: "Annotation canvas", exact: true })
    : h.page.getByRole("application", {
        name: "Annotation canvas",
        exact: true,
      });
  await canvas.focus();
  await h.page.keyboard.press("+");
  if (keypoints)
    await h.page
      .getByRole("region", { name: "Skeleton keypoints", exact: true })
      .getByRole("button", { name: "Pan image", exact: true })
      .click();
  else await h.button("Pan image").click();
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
    if (keypoints && moves % 20 === 0)
      await h.page.mouse.wheel(0, moves % 40 === 0 ? -30 : 30);
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

async function coordinateAccuracy(h) {
  const taskId = h.manifest.projects.keypoints.task_ids[5];
  await h.open("keypoints", taskId);
  const canvas = h.page
    .getByRole("region", { name: "Skeleton keypoints", exact: true })
    .getByRole("application", { name: "Annotation canvas", exact: true });
  const bounds = await canvas.locator("canvas").first().boundingBox();
  assert.ok(bounds);
  const cx = bounds.x + bounds.width / 2,
    cy = bounds.y + bounds.height / 2;
  const fit = Math.min(bounds.width / 2000, bounds.height / 1500);
  async function point() {
    await h.save();
    return (await h.latest(taskId)).annotation.keypoints.at(-1).points;
  }
  await h.page.mouse.click(cx, cy);
  const first = await point();
  assert.ok(
    Math.abs(first[0].x - 1000) <= 1 && Math.abs(first[0].y - 750) <= 1,
  );
  for (let step = 0; step < 14; step += 1) await h.page.keyboard.press("+");
  await h.page.mouse.click(cx + 100, cy);
  const zoomed = await point();
  const scale = fit * 20;
  const expectedZoom = [1000 + 100 / scale, 750];
  assert.ok(
    Math.abs(zoomed[1].x - expectedZoom[0]) <= 1 &&
      Math.abs(zoomed[1].y - expectedZoom[1]) <= 1,
  );
  await h.page.keyboard.press("Alt+ArrowRight");
  await h.page.mouse.click(cx + 100, cy + 60);
  const panned = await point();
  const expectedPan = [1000 + (100 - 30) / scale, 750 + 60 / scale];
  assert.ok(
    Math.abs(panned[1].x - expectedPan[0]) <= 1 &&
      Math.abs(panned[1].y - expectedPan[1]) <= 1,
  );
  const revisionsBefore = (await h.task(taskId)).revisions.length;
  await h.page.mouse.move(cx + 100, cy + 60);
  await h.page.mouse.down();
  await h.page.mouse.move(cx + 140, cy + 80, { steps: 8 });
  await h.page.mouse.up();
  const dragged = await point();
  const expectedDrag = [
    expectedPan[0] + 40 / scale,
    expectedPan[1] + 20 / scale,
  ];
  const errors = [
    Math.abs(dragged[1].x - expectedDrag[0]),
    Math.abs(dragged[1].y - expectedDrag[1]),
  ];
  assert.ok(
    errors.every((error) => error <= 1),
    `Drag errors ${errors.join(",")}`,
  );
  assert.equal((await h.task(taskId)).revisions.length, revisionsBefore + 1);
  return {
    kind: "coordinate-accuracy",
    taskId,
    fit,
    zoom: 20,
    errors,
    dragRevisions: 1,
  };
}

export async function largeImages(h) {
  const checks = [];
  for (const [kind, width, height] of [
    ["large4k", 3840, 2160],
    ["large4k-keypoints", 3840, 2160],
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
    if (kind === "large4k-keypoints") {
      assert.equal(baseline.keypoints.length, 50);
      assert.ok(
        baseline.keypoints.every((skeleton) => skeleton.points.length === 17),
      );
    }
    const measurement = await panFrames(h, kind === "large4k-keypoints");
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
  checks.push(await coordinateAccuracy(h));
  return checks;
}
