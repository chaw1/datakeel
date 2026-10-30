import { act, render, screen } from "@testing-library/react";
import { useImperativeHandle } from "react";
import { expect, it, vi } from "vitest";

import { BboxEditor } from "./BboxEditor";
import { PolygonEditor } from "./PolygonEditor";

import type { AnnotationRecord, EditorProps } from "./types";
import type { ReactNode, Ref } from "react";

// Konva stand-ins. The stage keeps its latest handlers so a test can press, drag and release;
// groups and chips expose whether they take pointer events; the text reports a natural width
// so a long name is measured and truncated as on a real canvas.
const stage = vi.hoisted(() => {
  const handlers: Record<string, ((event: unknown) => void) | undefined> = {};
  return { handlers };
});
vi.mock("react-konva", async () => {
  const { createElement } = await import("react");
  const node = ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children);
  return {
    Stage: ({
      children,
      ...handlers
    }: {
      children?: ReactNode;
    } & Record<string, (event: unknown) => void>) => {
      stage.handlers = handlers;
      return createElement("div", null, children);
    },
    Layer: node,
    Image: node,
    Rect: node,
    Transformer: node,
    Circle: node,
    Tag: node,
    Line: ({ points, dash }: { points: number[]; dash?: number[] }) =>
      createElement("div", {
        "data-testid": dash ? "draft" : "line",
        "data-points": String(points.length / 2),
      }),
    Group: ({
      children,
      listening,
    }: {
      children?: ReactNode;
      listening?: boolean;
    }) =>
      createElement(
        "div",
        { "data-listening": String(listening ?? true) },
        children,
      ),
    Label: ({
      children,
      listening,
    }: {
      children?: ReactNode;
      listening?: boolean;
    }) =>
      createElement(
        "div",
        { "data-testid": "chip", "data-listening": String(listening ?? true) },
        children,
      ),
    Text: ({
      ref,
      text,
      ellipsis,
    }: {
      ref?: Ref<{ getTextWidth: () => number }>;
      text: string;
      ellipsis?: boolean;
    }) => {
      useImperativeHandle(ref, () => ({ getTextWidth: () => text.length * 7 }));
      return createElement(
        "span",
        { "data-ellipsis": String(Boolean(ellipsis)) },
        text,
      );
    },
  };
});

const LONG = "Refrigerated beverage display cabinet with glass doors";
const labels = [{ id: "long", name: LONG, shortcut: "1", attributes: {} }];

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

/**
 * Press at a screen point where the chip is drawn, then optionally drag and release. As in
 * Konva, the press lands on the chip when it and every group above it listen, and otherwise
 * on the image background beneath it.
 */
function pressOnChip(
  chip: HTMLElement,
  from: { x: number; y: number },
  to?: { x: number; y: number },
) {
  let pointer = from;
  const container = document.createElement("div");
  const konvaStage = {
    getPointerPosition: () => pointer,
    container: () => container,
    find: () => [],
  };
  const catches = chip.closest('[data-listening="false"]') === null;
  const target = {
    name: () => (catches ? "wb-shape-label" : "wb-canvas-background"),
    getStage: () => konvaStage,
  };
  const background = {
    name: () => "wb-canvas-background",
    getStage: () => konvaStage,
  };
  act(() => {
    stage.handlers.onMouseDown?.({ target, evt: {} });
  });
  if (to) {
    pointer = to;
    act(() => {
      stage.handlers.onMouseMove?.({ target: background, evt: {} });
    });
  }
  act(() => {
    stage.handlers.onMouseUp?.({ target: background, evt: {} });
  });
}

function truncatedChip() {
  const chip = screen.getByTestId("chip");
  // The 600-pixel-wide shape is 144 pixels on screen, too narrow for the full name.
  expect(
    chip.querySelector("[data-ellipsis]")?.getAttribute("data-ellipsis"),
  ).toBe("true");
  return chip;
}

it("draws a new box when the drag starts on a truncated label chip", () => {
  const onChange = vi.fn<(value: AnnotationRecord) => void>();
  render(
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
            category: "long",
            x1: 100,
            y1: 300,
            x2: 700,
            y2: 900,
            attributes: {},
          },
        ],
      }}
      onChange={onChange}
    />,
  );
  // The 3000x2000 image fits the 720x480 canvas at 24%; the chip sits just above the box.
  pressOnChip(truncatedChip(), { x: 34, y: 63 }, { x: 94, y: 3 });
  expect(onChange).toHaveBeenCalledTimes(1);
  const boxes = onChange.mock.calls[0]?.[0].boxes ?? [];
  expect(boxes).toHaveLength(2);
  expect(boxes[1]?.x2 ?? 0).toBeGreaterThan(boxes[1]?.x1 ?? 0);
});

it("adds polygon points, the first one included, when pressing on a truncated label chip", () => {
  render(
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
            category: "long",
            points: [
              { x: 100, y: 300 },
              { x: 700, y: 300 },
              { x: 400, y: 900 },
            ],
            attributes: {},
          },
        ],
      }}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByTestId("draft")).toBeNull();
  // Not drawing yet: the press on the chip starts a polygon at that point.
  pressOnChip(truncatedChip(), { x: 34, y: 63 });
  expect(screen.getByTestId("draft").dataset.points).toBe("2");
  // Drawing: a further press on the chip adds the next point.
  pressOnChip(truncatedChip(), { x: 40, y: 64 });
  expect(screen.getByTestId("draft").dataset.points).toBe("3");
});
