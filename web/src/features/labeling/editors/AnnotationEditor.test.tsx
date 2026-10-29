import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { AnnotationEditor } from "./AnnotationEditor";

import type {
  AnnotationRecord,
  EditorProps,
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
  };
});
const labels = [
  { id: "cat", name: "Cat", shortcut: "1", attributes: {} },
  { id: "dog", name: "Dog", shortcut: "2", attributes: {} },
];
const empty: AnnotationRecord = {
  sample_id: "sample",
  annotator_id: "local",
  image_width: 2000,
  image_height: 1500,
};
function mount(
  type: ProductionTemplate["annotation_type"],
  options: Partial<EditorProps> = {},
) {
  const changed = vi.fn<(value: AnnotationRecord) => void>();
  function Harness() {
    const [value, setValue] = useState(options.value ?? empty);
    return (
      <>
        <AnnotationEditor
          labels={labels}
          template={{
            id: "template",
            name: "Template",
            annotation_type: type,
            revision: 1,
            archived: false,
            component_config: {},
            ...options.template,
          }}
          {...options}
          value={value}
          onChange={(next) => {
            changed(next);
            setValue(next);
          }}
        />
        <output data-testid="annotation">{JSON.stringify(value)}</output>
      </>
    );
  }
  render(<Harness />);
  const annotation = () =>
    JSON.parse(
      screen.getByTestId("annotation").textContent,
    ) as AnnotationRecord;
  return { changed, annotation };
}
describe("box editor", () => {
  it("adds, moves, resizes, copies and deletes a box using keyboard events", () => {
    const { annotation } = mount("box");
    const editor = screen.getByRole("region", { name: "Bounding boxes" });
    fireEvent.keyDown(editor, { key: "b" });
    expect(annotation().boxes).toEqual([
      { category: "cat", x1: 200, y1: 150, x2: 600, y2: 450, attributes: {} },
    ]);
    fireEvent.keyDown(editor, { key: "ArrowRight" });
    fireEvent.keyDown(editor, { key: "ArrowDown", shiftKey: true });
    expect(annotation().boxes?.[0]).toMatchObject({
      x1: 201,
      x2: 601,
      y2: 451,
    });
    fireEvent.keyDown(editor, { key: "d", ctrlKey: true });
    expect(annotation().boxes?.[1]).toMatchObject({ x1: 211, y1: 160 });
    fireEvent.keyDown(editor, { key: "Delete" });
    expect(annotation().boxes).toHaveLength(1);
  });
  it("changes native pixel coordinates, label and nested properties without altering unrelated data", () => {
    const { annotation } = mount("box", {
      value: { ...empty, labels: ["dog"], attributes: { source: "fixture" } },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add box (B)" }));
    fireEvent.change(screen.getByLabelText("Left (x1)"), {
      target: { value: "213.5" },
    });
    fireEvent.change(screen.getByLabelText("Label"), {
      target: { value: "dog" },
    });
    fireEvent.change(screen.getByLabelText("Properties (JSON)"), {
      target: { value: '{"reviewed":true,"meta":{"score":0.5}}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply properties" }));
    expect(annotation()).toMatchObject({
      labels: ["dog"],
      attributes: { source: "fixture" },
      boxes: [
        {
          x1: 213.5,
          category: "dog",
          attributes: { reviewed: true, meta: { score: 0.5 } },
        },
      ],
    });
  });
});
describe("classification editor", () => {
  it("toggles multiple labels with shortcuts and keeps record properties", () => {
    const { annotation } = mount("classification", {
      template: {
        id: "multi",
        name: "Multi",
        component_config: { multiple: true },
        annotation_type: "classification",
        revision: 1,
        archived: false,
      },
    });
    const editor = screen.getByRole("region", { name: "Classification" });
    fireEvent.keyDown(editor, { key: "1" });
    fireEvent.keyDown(editor, { key: "2" });
    expect(annotation().labels).toEqual(["cat", "dog"]);
    fireEvent.keyDown(editor, { key: "1" });
    expect(annotation().labels).toEqual(["dog"]);
    fireEvent.change(screen.getByLabelText("Properties (JSON)"), {
      target: { value: "[]" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply properties" }));
    expect(screen.getByRole("alert")).toHaveTextContent("valid JSON object");
    expect(annotation().attributes).toBeUndefined();
  });
  it("supports native radio selection and enforces read-only controls", () => {
    const { annotation, changed } = mount("classification", {
      readOnly: true,
      value: { ...empty, labels: ["cat"] },
    });
    expect(screen.getByRole("radio", { name: "Cat 1" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("region", { name: "Classification" }), {
      key: "2",
    });
    expect(annotation().labels).toEqual(["cat"]);
    expect(changed).not.toHaveBeenCalled();
  });
});
it("draws and edits polygon vertices entirely through keyboard events", () => {
  const { annotation } = mount("polygon");
  const editor = screen.getByRole("region", { name: "Polygons" });
  for (const key of [
    "p",
    " ",
    "ArrowRight",
    " ",
    "ArrowDown",
    " ",
    "ArrowLeft",
    " ",
    "Enter",
  ])
    fireEvent.keyDown(editor, { key });
  expect(annotation().polygons?.[0]?.points).toEqual([
    { x: 1000, y: 750 },
    { x: 1010, y: 750 },
    { x: 1010, y: 760 },
    { x: 1000, y: 760 },
  ]);
  fireEvent.keyDown(editor, { key: "ArrowUp", shiftKey: true });
  expect(annotation().polygons?.[0]?.points[0]).toEqual({ x: 1000, y: 749 });
  fireEvent.keyDown(editor, { key: "Backspace" });
  expect(annotation().polygons?.[0]?.points).toHaveLength(3);
  fireEvent.keyDown(editor, { key: "ArrowRight" });
  expect(annotation().polygons?.[0]?.points[0]).toEqual({ x: 1011, y: 750 });
});
it("labels nested Unicode selections and preserves code-point coordinates", () => {
  const { annotation } = mount("text_span", { text: "A😀中文 nested" });
  const source = screen.getByRole("textbox", {
    name: "Source text: select a range, then press Enter",
  });
  if (!(source instanceof HTMLTextAreaElement))
    throw new Error("Source is not a textarea");
  source.setSelectionRange(1, 6);
  fireEvent.select(source);
  fireEvent.keyDown(source, { key: "Enter" });
  source.setSelectionRange(3, 5);
  fireEvent.select(source);
  fireEvent.keyDown(source, { key: "Enter" });
  expect(annotation().spans).toEqual([
    { category: "cat", start: 1, end: 5, attributes: {} },
    { category: "cat", start: 2, end: 4, attributes: {} },
  ]);
  expect(annotation().text_length).toBe(Array.from("A😀中文 nested").length);
  fireEvent.keyDown(source, { key: "Enter", ctrlKey: true });
  expect(annotation().spans).toHaveLength(2);
  expect(document.querySelector('[data-nested="true"]')).toHaveTextContent(
    "中文",
  );
  fireEvent.click(screen.getByRole("button", { name: "Delete annotation" }));
  expect(annotation().spans).toHaveLength(1);
});
it("dispatches multiple configured components through the same annotation record", () => {
  mount("box", {
    template: {
      id: "mix",
      name: "Mixed",
      annotation_type: "box",
      revision: 1,
      archived: false,
      component_config: {
        components: ["bbox", "classification", "polygon", "span"],
      },
    },
  });
  for (const name of [
    "Bounding boxes",
    "Classification",
    "Polygons",
    "Text spans",
  ])
    expect(screen.getByRole("region", { name })).toBeInTheDocument();
});

it("preserves source coordinates when textarea normalizes CRLF newlines", () => {
  const { annotation } = mount("text_span", { text: "A😀\r\n猫 B" });
  const source = screen.getByRole("textbox", {
    name: "Source text: select a range, then press Enter",
  });
  if (!(source instanceof HTMLTextAreaElement))
    throw new Error("Source is not a textarea");
  source.setSelectionRange(4, 5);
  fireEvent.select(source);
  fireEvent.keyDown(source, { key: "Enter" });
  expect(annotation().spans?.[0]).toMatchObject({ start: 4, end: 5 });
  expect(annotation().text_length).toBe(7);
});
