import { act, render } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { BboxEditor } from "./BboxEditor";
import { PolygonEditor } from "./PolygonEditor";

import type { EditorProps } from "./types";
import type { ReactNode } from "react";

// Konva stand-ins that keep drawing order as document order: each node is an element tagged
// with its kind, and a chip carries its name. The stage keeps its handlers so a test can press.
const stage = vi.hoisted(() => {
  const handlers: Record<string, ((event: unknown) => void) | undefined> = {};
  return { handlers };
});
vi.mock("react-konva", async () => {
  const { createElement } = await import("react");
  const kind =
    (name: string) =>
    ({ children }: { children?: ReactNode }) =>
      createElement("div", { "data-kind": name }, children);
  return {
    Stage: ({
      children,
      ...handlers
    }: { children?: ReactNode } & Record<string, (event: unknown) => void>) => {
      stage.handlers = handlers;
      return createElement("div", null, children);
    },
    Layer: kind("layer"),
    Group: kind("group"),
    Image: kind("image"),
    Rect: kind("shape"),
    Line: kind("shape"),
    Circle: kind("handle"),
    Transformer: kind("handle"),
    Tag: kind("tag"),
    Label: kind("chip"),
    Text: ({ text }: { text: string }) => createElement("span", null, text),
  };
});

const labels = [
  { id: "shelf", name: "Shelf", shortcut: "1", attributes: {} },
  { id: "cart", name: "Cart", shortcut: "2", attributes: {} },
];

function template(kind: "box" | "polygon"): EditorProps["template"] {
  return {
    id: kind,
    name: kind,
    annotation_type: kind,
    revision: 1,
    archived: false,
    attributes: [],
    component_config: {},
  };
}

/** Every shape and draft is drawn before the first chip; chips follow in shape order. */
function expectChipsOnTop(container: HTMLElement, names: string[]) {
  const nodes = [...container.querySelectorAll<HTMLElement>("[data-kind]")];
  const kinds = nodes.map((node) => node.dataset.kind);
  expect(kinds.lastIndexOf("shape")).toBeLessThan(kinds.indexOf("chip"));
  const chips = nodes.filter((node) => node.dataset.kind === "chip");
  expect(chips.map((chip) => chip.textContent)).toEqual(names);
}

/** Press on the image background, then optionally move the pointer there. */
function pressBackground(to?: { x: number; y: number }) {
  let pointer = { x: 300, y: 200 };
  const konvaStage = {
    getPointerPosition: () => pointer,
    container: () => document.createElement("div"),
    find: () => [],
  };
  const background = {
    name: () => "wb-canvas-background",
    getStage: () => konvaStage,
  };
  act(() => {
    stage.handlers.onMouseDown?.({ target: background, evt: {} });
  });
  if (!to) return;
  pointer = to;
  act(() => {
    stage.handlers.onMouseMove?.({ target: background, evt: {} });
  });
}

it("draws box chips above every box, so a later box never covers an earlier name", () => {
  const { container } = render(
    <BboxEditor
      labels={labels}
      template={template("box")}
      value={{
        sample_id: "sample",
        annotator_id: "local",
        image_width: 3000,
        image_height: 2000,
        boxes: [
          {
            category: "shelf",
            x1: 100,
            y1: 300,
            x2: 700,
            y2: 900,
            attributes: {},
          },
          // Drawn later and larger: it lies over the shelf's chip.
          {
            category: "cart",
            x1: 50,
            y1: 100,
            x2: 900,
            y2: 1000,
            attributes: {},
          },
        ],
      }}
      onChange={vi.fn()}
    />,
  );
  expectChipsOnTop(container, ["Shelf", "Cart"]);
  // The dashed box being drawn stays beneath the names too.
  const before = container.querySelectorAll('[data-kind="shape"]').length;
  pressBackground({ x: 400, y: 300 });
  expect(container.querySelectorAll('[data-kind="shape"]')).toHaveLength(
    before + 1,
  );
  expectChipsOnTop(container, ["Shelf", "Cart"]);
});

it("draws polygon chips above every polygon and the polygon being drawn", () => {
  const { container } = render(
    <PolygonEditor
      labels={labels}
      template={template("polygon")}
      value={{
        sample_id: "sample",
        annotator_id: "local",
        image_width: 3000,
        image_height: 2000,
        polygons: [
          {
            category: "shelf",
            points: [
              { x: 100, y: 300 },
              { x: 700, y: 300 },
              { x: 400, y: 900 },
            ],
            attributes: {},
          },
          {
            category: "cart",
            points: [
              { x: 50, y: 100 },
              { x: 900, y: 100 },
              { x: 500, y: 1000 },
            ],
            attributes: {},
          },
        ],
      }}
      onChange={vi.fn()}
    />,
  );
  expectChipsOnTop(container, ["Shelf", "Cart"]);
  const before = container.querySelectorAll('[data-kind="shape"]').length;
  pressBackground();
  expect(
    container.querySelectorAll('[data-kind="shape"]').length,
  ).toBeGreaterThan(before);
  expectChipsOnTop(container, ["Shelf", "Cart"]);
});
