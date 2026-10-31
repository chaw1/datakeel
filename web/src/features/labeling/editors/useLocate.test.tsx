import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { AnnotationEditor } from "./AnnotationEditor";

import type {
  AnnotationRecord,
  LocateRequest,
  ProductionTemplate,
} from "./types";
import type { ReactNode } from "react";

vi.mock("react-konva", async () => {
  const { createElement } = await import("react");
  const node = ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children);
  return {
    Stage: node,
    Layer: node,
    Group: node,
    Image: node,
    Rect: node,
    Transformer: node,
    Circle: node,
    Line: node,
    Label: node,
    Tag: node,
    Text: node,
  };
});

const labels = [{ id: "cat", name: "Cat", attributes: {} }];
const value: AnnotationRecord = {
  sample_id: "sample",
  annotator_id: "reviewer",
  image_width: 2000,
  image_height: 1500,
  text_length: 11,
  boxes: [
    { category: "cat", x1: 1, y1: 1, x2: 20, y2: 20 },
    { category: "cat", x1: 30, y1: 30, x2: 60, y2: 60 },
  ],
  polygons: [
    {
      category: "cat",
      points: [
        { x: 1, y: 1 },
        { x: 9, y: 1 },
        { x: 9, y: 9 },
      ],
    },
    {
      category: "cat",
      points: [
        { x: 20, y: 20 },
        { x: 29, y: 20 },
        { x: 29, y: 29 },
      ],
    },
  ],
  spans: [
    { category: "cat", start: 0, end: 3 },
    { category: "cat", start: 4, end: 9 },
  ],
};
function template(components: string[]): ProductionTemplate {
  return {
    id: "template",
    name: "Template",
    annotation_type: "box",
    revision: 1,
    archived: false,
    attributes: [],
    component_config: { components },
  };
}
function editor(components: string[], request: LocateRequest | null) {
  return (
    <AnnotationEditor
      value={value}
      onChange={vi.fn()}
      labels={labels}
      template={template(components)}
      text="cat sat mat"
      readOnly
      locate={request}
    />
  );
}

it("selects the located box or polygon in a read-only editor, again on every request", () => {
  const { rerender } = render(editor(["box", "polygon"], null));
  const [boxes, polygons] = screen.getAllByRole("combobox", {
    name: "Selected annotation",
  });
  expect(boxes).toHaveValue("-1");
  rerender(editor(["box", "polygon"], { kind: "box", index: 1 }));
  expect(boxes).toHaveValue("1");
  // Another request for a polygon leaves the box editor alone.
  rerender(editor(["box", "polygon"], { kind: "polygon", index: 1 }));
  expect(polygons).toHaveValue("1");
  expect(boxes).toHaveValue("1");
  rerender(editor(["box", "polygon"], { kind: "box", index: 0 }));
  expect(boxes).toHaveValue("0");
});

it("selects a located text span", () => {
  const { rerender } = render(editor(["span"], null));
  const list = screen.getByRole("list", { name: "Text annotations" });
  const [, second] = within(list).getAllByRole("button");
  expect(second).toHaveAttribute("aria-pressed", "false");
  rerender(editor(["span"], { kind: "span", index: 1 }));
  expect(second).toHaveAttribute("aria-pressed", "true");
});
