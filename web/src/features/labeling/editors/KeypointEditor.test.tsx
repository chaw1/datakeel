import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { AnnotationEditor } from "./AnnotationEditor";

import type {
  AnnotationRecord,
  EditorProps,
  ProductionTemplate,
  SkeletonDefinition,
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

const schema: SkeletonDefinition = {
  points: [
    { id: "nose", name: "Nose", required: true },
    { id: "neck", name: "Neck", required: false },
  ],
  edges: [["nose", "neck"]],
};
const labels = [
  { id: "person", name: "Person", shortcut: "1", attributes: {} },
  { id: "dog", name: "Dog", shortcut: "2", attributes: {} },
];
const empty: AnnotationRecord = {
  sample_id: "sample",
  annotator_id: "local",
  image_width: 2000,
  image_height: 1500,
};

function mount(options: Partial<EditorProps> = {}) {
  const changed = vi.fn<(value: AnnotationRecord) => void>();
  const template: ProductionTemplate = {
    id: "pose",
    name: "Pose",
    annotation_type: "keypoints",
    revision: 1,
    archived: false,
    attributes: [],
    component_config: {},
    keypoint_schema: schema,
    ...options.template,
  };
  function Harness() {
    const [value, setValue] = useState(options.value ?? empty);
    return (
      <>
        <AnnotationEditor
          labels={labels}
          {...options}
          template={template}
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
  return {
    changed,
    annotation: () =>
      JSON.parse(
        screen.getByTestId("annotation").textContent,
      ) as AnnotationRecord,
  };
}

it("creates multiple skeletons and edits tri-state points entirely by keyboard", () => {
  const { annotation } = mount();
  const editor = screen.getByRole("region", { name: "Skeleton keypoints" });
  fireEvent.keyDown(editor, { key: "k" });
  expect(annotation().keypoints?.[0]?.points).toEqual([
    { id: "nose", state: "missing" },
    { id: "neck", state: "missing" },
  ]);
  fireEvent.keyDown(editor, { key: " " });
  expect(annotation().keypoints?.[0]?.points[0]).toMatchObject({
    x: 1000,
    y: 750,
    state: "visible",
  });
  fireEvent.keyDown(editor, { key: "ArrowRight", shiftKey: true });
  expect(annotation().keypoints?.[0]?.points[1].x).toBeUndefined();
  fireEvent.keyDown(editor, { key: " " });
  fireEvent.keyDown(editor, { key: "v" });
  fireEvent.keyDown(editor, { key: "ArrowLeft" });
  expect(annotation().keypoints?.[0]?.points[1]).toMatchObject({
    x: 1009,
    y: 750,
    state: "occluded",
  });
  fireEvent.keyDown(editor, { key: "k" });
  fireEvent.keyDown(editor, { key: " " });
  expect(annotation().keypoints).toHaveLength(2);
  expect(annotation().keypoints?.[1]?.points[0].state).toBe("visible");
  fireEvent.change(screen.getByLabelText("Label"), {
    target: { value: "dog" },
  });
  expect(annotation().keypoints?.[1]?.category).toBe("dog");
  expect(annotation().keypoints?.[0]?.category).toBe("person");
  fireEvent.keyDown(editor, { key: "[" });
  fireEvent.keyDown(editor, { key: "x" });
  expect(annotation().keypoints?.[1]?.points[0]).toEqual({
    id: "nose",
    state: "missing",
    x: null,
    y: null,
  });
});

it("uses native point, coordinate and skeleton attribute controls", () => {
  const { annotation } = mount({
    template: {
      id: "pose",
      name: "Pose",
      annotation_type: "keypoints",
      revision: 1,
      archived: false,
      component_config: {},
      keypoint_schema: schema,
      attributes: [
        {
          key: "side",
          name_zh: "侧面",
          name_en: "Side",
          type: "text",
          required: false,
          options: [],
          target: "object",
          max_length: 20,
        },
      ],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add skeleton (K)" }));
  fireEvent.click(screen.getByRole("button", { name: "Nose · missing" }));
  fireEvent.change(screen.getByLabelText("Point state"), {
    target: { value: "visible" },
  });
  // A native state change creates an explicit positioned point, never a missing (0,0).
  expect(annotation().keypoints?.[0]?.points[0]).toMatchObject({
    state: "visible",
    x: 0,
    y: 0,
  });
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Skeleton keypoints" }),
    {
      key: " ",
    },
  );
  fireEvent.click(screen.getByRole("button", { name: "Nose · visible" }));
  fireEvent.change(screen.getByLabelText("Point x"), {
    target: { value: "123.5" },
  });
  expect(annotation().keypoints?.[0]?.points[0].x).toBe(123.5);
  fireEvent.change(screen.getByLabelText("Side"), {
    target: { value: "left" },
  });
  expect(annotation().keypoints?.[0]?.attributes).toEqual({ side: "left" });
});

it("aligns an old revision to a newer schema on its next edit", () => {
  const { annotation } = mount({
    value: {
      ...empty,
      keypoints: [
        {
          category: "person",
          points: [{ id: "nose", x: 10, y: 20, state: "visible" }],
          attributes: {},
        },
      ],
    },
  });
  fireEvent.click(screen.getByRole("button", { name: "Add skeleton (K)" }));
  expect(annotation().keypoints?.[0]?.points).toEqual([
    { id: "nose", x: 10, y: 20, state: "visible" },
    { id: "neck", state: "missing" },
  ]);
});

it("keeps read-only review rendering and controls unchanged", () => {
  const { changed } = mount({ readOnly: true });
  fireEvent.keyDown(
    screen.getByRole("region", { name: "Skeleton keypoints" }),
    {
      key: "k",
    },
  );
  expect(changed).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "Add skeleton (K)" }),
  ).toBeDisabled();
});

it("registers keypoints beside existing components in a mixed template", () => {
  mount({
    template: {
      id: "mixed",
      name: "Mixed",
      annotation_type: "box",
      revision: 1,
      archived: false,
      attributes: [],
      component_config: { components: ["box", "keypoints", "classification"] },
      keypoint_schema: schema,
    },
  });
  for (const name of ["Bounding boxes", "Skeleton keypoints", "Classification"])
    expect(screen.getByRole("region", { name })).toBeInTheDocument();
});
