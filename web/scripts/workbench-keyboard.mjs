import assert from "node:assert/strict";

import {
  poll,
  selectedAnnotation,
  tabTo,
  textStartKey,
} from "./workbench-helpers.mjs";

const regions = {
  box: "Bounding boxes",
  polygon: "Polygons",
  classification: "Classification",
  text_span: "Text spans",
};

export async function addWithKeyboard(h, kind) {
  const { page } = h;
  const region = page.getByRole("region", { name: regions[kind], exact: true });
  if (["box", "polygon"].includes(kind)) {
    await tabTo(
      page,
      region.getByRole("application", {
        name: "Annotation canvas",
        exact: true,
      }),
    );
    if (kind === "box") await page.keyboard.press("b");
    else
      for (const key of [
        "p",
        "Space",
        "Shift+ArrowRight",
        "Space",
        "Shift+ArrowDown",
        "Space",
        "Enter",
      ])
        await page.keyboard.press(key);
  } else if (kind === "classification") {
    const input = region
      .locator('input[type="radio"],input[type="checkbox"]')
      .first();
    await tabTo(page, input);
    await page.keyboard.press("2");
  } else {
    await tabTo(
      page,
      region.getByRole("textbox", {
        name: "Source text: select a range, then press Enter",
        exact: true,
      }),
    );
    await page.keyboard.press(textStartKey);
    for (let step = 0; step < 5; step += 1)
      await page.keyboard.press("Shift+ArrowRight");
    await page.keyboard.press("Enter");
  }
}

export async function keyboardWorkflow(h) {
  const checks = [];
  const countPointers = () => {
    if (globalThis.__workbenchPointerEvents !== undefined) return;
    globalThis.__workbenchPointerEvents = 0;
    globalThis.document.addEventListener(
      "pointerdown",
      () => {
        globalThis.__workbenchPointerEvents += 1;
      },
      true,
    );
  };
  // Later loads get the counter from the init script; the document an earlier
  // phase (W1) left open only changes its hash, so install it there as well.
  await h.page.addInitScript(countPointers);
  await h.page.evaluate(countPointers);
  for (const kind of Object.keys(regions)) {
    const taskId = await h.editableTask(kind);
    const before = await h.latest(taskId);
    await h.open(kind, taskId, true);
    await tabTo(h.page, h.button("Keyboard shortcuts"));
    await h.page.keyboard.press("?");
    await h.page
      .getByRole("heading", { name: "Keyboard shortcuts", exact: true })
      .waitFor();
    await tabTo(h.page, h.button("Close"));
    await h.page.keyboard.press("Enter");
    await addWithKeyboard(h, kind);
    await h.save();
    const saved = await h.latest(taskId);
    assert.notEqual(
      saved.id,
      before.id,
      `${kind}: keyboard action must create a revision`,
    );
    const field = {
      box: "boxes",
      polygon: "polygons",
      classification: "labels",
      text_span: "spans",
    }[kind];
    if (kind === "classification")
      assert.notDeepEqual(saved.annotation.labels, before.annotation.labels);
    else
      assert.equal(
        saved.annotation[field].length,
        (before.annotation[field]?.length ?? 0) + 1,
      );
    await tabTo(h.page, h.button("Mark complete"));
    await h.page.keyboard.press("Control+Enter");
    const submitted = await poll(
      () => h.task(taskId),
      (value) => value.task.state === "approved",
      `${kind} personal submission`,
    );
    assert.equal(submitted.task.approved_revision_id, saved.id);
    assert.equal(
      await h.page.evaluate(() => globalThis.__workbenchPointerEvents),
      0,
      `${kind}: annotation, save and submit must use keyboard events only`,
    );
    checks.push({
      kind,
      taskId,
      revision: saved.id,
      state: submitted.task.state,
      input: "Tab and keyboard events only",
    });
    await h.capture(`W2-${kind}`);
  }
  return checks;
}

async function historyEditor(h, kind, annotation) {
  const { page } = h;
  if (["box", "polygon"].includes(kind))
    await selectedAnnotation(page).selectOption("0");
  if (kind === "text_span")
    await page
      .getByRole("list", { name: "Text annotations", exact: true })
      .getByRole("button")
      .first()
      .click();
  if (kind === "classification") {
    const region = page.getByRole("region", {
      name: "Classification",
      exact: true,
    });
    await tabTo(page, region.locator("input").first());
    const base = [...annotation.labels];
    return {
      edit: (step) => page.keyboard.press(step % 2 ? "1" : "2"),
      current: () =>
        region
          .locator("input:checked")
          .evaluateAll((nodes) => nodes.map((node) => node.value)),
      baseline: base,
    };
  }
  const [name, baseline] =
    kind === "box"
      ? ["Left (x1)", annotation.boxes[0].x1]
      : kind === "polygon"
        ? ["Point x", annotation.polygons[0].points[0].x]
        : ["End character (exclusive)", annotation.spans[0].end];
  const field = page.getByRole("spinbutton", { name, exact: true });
  return {
    edit: (step) => field.fill(String(baseline + (step % 2 ? 0 : 1))),
    current: async () => Number(await field.inputValue()),
    baseline,
  };
}

export async function unlimitedHistory(h) {
  const checks = [];
  for (const kind of Object.keys(regions)) {
    const taskId = await h.editableTask(kind, kind === "box" ? 2 : 1);
    const baseline = (await h.latest(taskId)).annotation;
    await h.open(kind, taskId);
    const editor = await historyEditor(h, kind, baseline);
    for (let step = 0; step < 200; step += 1) await editor.edit(step);
    await tabTo(h.page, h.button("Keyboard shortcuts"));
    assert.equal(await h.button("Undo").isEnabled(), true);
    await h.page.keyboard.press("Control+z");
    assert.notDeepEqual(await editor.current(), editor.baseline);
    for (let step = 0; step < 199; step += 1)
      await h.page.keyboard.press("Control+z");
    assert.deepEqual(await editor.current(), editor.baseline);
    assert.equal(
      await h.button("Undo").isDisabled(),
      true,
      `${kind}: exactly 200 undo steps`,
    );
    assert.equal(await h.button("Redo").isEnabled(), true);
    await h.page.keyboard.press("Control+Shift+z");
    assert.notDeepEqual(await editor.current(), editor.baseline);
    for (let step = 0; step < 199; step += 1)
      await h.page.keyboard.press("Control+Shift+z");
    assert.deepEqual(await editor.current(), editor.baseline);
    assert.equal(
      await h.button("Redo").isDisabled(),
      true,
      `${kind}: exactly 200 redo steps`,
    );
    await h.save();
    assert.deepEqual(
      (await h.latest(taskId)).annotation,
      baseline,
      `${kind}: full record survives 200 undo/redo`,
    );
    checks.push({
      kind,
      taskId,
      edits: 200,
      undo: 200,
      redo: 200,
      fullRecordRoundtrip: true,
    });
  }
  return checks;
}
