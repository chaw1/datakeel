import { expect, it } from "vitest";

import { labelShortcut, shortcutLabel } from "./shortcuts";

import type { ProductionTemplate } from "./types";

const cat = { id: "cat", name: "Cat", shortcut: "1" };
const dog = { id: "dog", name: "Dog" };
const template: ProductionTemplate = {
  id: "template",
  name: "Template",
  annotation_type: "classification",
  revision: 2,
  archived: false,
  attributes: [],
  component_config: { shortcuts: { cat: "c", dog: "v" } },
};
it("uses versioned template label shortcuts before label defaults", () => {
  expect(labelShortcut(cat, 0, template)).toBe("c");
  expect(
    shortcutLabel(
      new KeyboardEvent("keydown", { key: "V" }),
      [cat, dog],
      template,
    ),
  ).toEqual(dog);
  expect(
    shortcutLabel(
      new KeyboardEvent("keydown", { key: "1" }),
      [cat, dog],
      template,
    ),
  ).toBeUndefined();
});
it("preserves native save and undo shortcuts for the parent", () => {
  expect(
    shortcutLabel(
      new KeyboardEvent("keydown", { key: "c", ctrlKey: true }),
      [cat],
      template,
    ),
  ).toBeUndefined();
  expect(labelShortcut(dog, 1, { ...template, component_config: {} })).toBe(
    "2",
  );
});
