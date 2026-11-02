import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, it, vi } from "vitest";

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
    Label: node,
    Tag: node,
    Text: node,
  };
});

const labels = [
  { id: "speech", name: "Speech", shortcut: "1", attributes: {} },
  { id: "noise", name: "Noise", shortcut: "2", attributes: {} },
];
const playMock = vi.fn<() => Promise<void>>();
const empty: AnnotationRecord = {
  sample_id: "sample",
  annotator_id: "local",
  segments: [],
  media_duration_ms: 10_000,
};

function mount(options: Partial<EditorProps> = {}) {
  const changed = vi.fn<(value: AnnotationRecord) => void>();
  const template: ProductionTemplate = {
    id: "segments",
    name: "Segments",
    annotation_type: "segment",
    revision: 1,
    archived: false,
    attributes: [
      {
        key: "side",
        name_zh: "说明",
        name_en: "Side",
        type: "text",
        required: false,
        options: [],
        target: "object",
        max_length: 20,
      },
    ],
    component_config: { components: ["segment"] },
    ...options.template,
  };
  function Harness() {
    const [value, setValue] = useState(options.value ?? empty);
    return (
      <>
        <AnnotationEditor
          labels={labels}
          mediaUrl="/media.wav"
          mediaType="audio/wav"
          durationMs={10_000}
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

beforeEach(() => {
  playMock.mockClear();
  playMock.mockResolvedValue();
  vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(playMock);
  vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(
    () => undefined,
  );
  Object.defineProperty(HTMLElement.prototype, "setPointerCapture", {
    value: vi.fn(),
    configurable: true,
  });
});

it("creates overlapping segments and edits labels, attributes and milliseconds by keyboard", () => {
  const { annotation } = mount();
  const editor = screen.getByRole("region", { name: "Audio/video segments" });
  fireEvent.keyDown(editor, { key: "t" });
  fireEvent.keyDown(editor, { key: "ArrowRight" });
  expect(annotation().segments?.[0]).toMatchObject({
    start_ms: 1,
    end_ms: 1001,
  });
  fireEvent.keyDown(editor, { key: "r" });
  fireEvent.keyDown(editor, { key: "ArrowLeft" });
  expect(annotation().segments?.[0].start_ms).toBe(0);
  fireEvent.keyDown(editor, { key: "r" });
  fireEvent.keyDown(editor, { key: "ArrowRight", shiftKey: true });
  expect(annotation().segments?.[0].end_ms).toBe(1011);
  fireEvent.keyDown(editor, { key: "t" });
  expect(annotation().segments).toHaveLength(2);
  fireEvent.change(screen.getByLabelText("Label"), {
    target: { value: "noise" },
  });
  fireEvent.change(screen.getByLabelText("Side"), {
    target: { value: "重叠" },
  });
  expect(annotation().segments?.[1]).toMatchObject({
    category: "noise",
    attributes: { side: "重叠" },
  });
  fireEvent.change(screen.getByLabelText("Start (milliseconds, inclusive)"), {
    target: { value: "5" },
  });
  expect(annotation().segments?.[1].start_ms).toBe(5);
});

it("keeps playback, seeking, zoom and selection out of the annotation record", () => {
  const { changed } = mount();
  const editor = screen.getByRole("region", { name: "Audio/video segments" });
  fireEvent.keyDown(editor, { key: " " });
  expect(playMock).toHaveBeenCalled();
  fireEvent.keyDown(editor, { key: "." });
  fireEvent.keyDown(editor, { key: "+" });
  fireEvent.keyDown(editor, { key: "0" });
  expect(changed).not.toHaveBeenCalled();
});

it("normalizes reverse pointer creation and commits one record edit on pointerup", () => {
  const { annotation, changed } = mount();
  const timeline = screen.getByRole("group", { name: /Segment timeline/ });
  vi.spyOn(timeline, "getBoundingClientRect").mockReturnValue({
    left: 0,
    width: 1000,
    top: 0,
    right: 1000,
    bottom: 100,
    height: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  fireEvent(
    timeline,
    new MouseEvent("pointerdown", { clientX: 800, button: 0, bubbles: true }),
  );
  fireEvent(
    timeline,
    new MouseEvent("pointermove", { clientX: 200, button: 0, bubbles: true }),
  );
  expect(screen.getByRole("button", { name: "speech" })).toBeInTheDocument();
  fireEvent(timeline, new MouseEvent("pointerup", { bubbles: true }));
  expect(annotation().segments).toHaveLength(1);
  expect(annotation().segments?.[0]).toMatchObject({
    start_ms: 2000,
    end_ms: 8000,
  });
  expect(changed).toHaveBeenCalledTimes(1);
});

it("does not create a zero-length pointer segment", () => {
  const { annotation, changed } = mount();
  const timeline = screen.getByRole("group", { name: /Segment timeline/ });
  vi.spyOn(timeline, "getBoundingClientRect").mockReturnValue({
    left: 0,
    width: 1000,
    top: 0,
    right: 1000,
    bottom: 100,
    height: 100,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  });
  fireEvent(
    timeline,
    new MouseEvent("pointerdown", { clientX: 200, button: 0, bubbles: true }),
  );
  fireEvent(timeline, new MouseEvent("pointerup", { bubbles: true }));
  expect(annotation().segments).toEqual([]);
  expect(changed).not.toHaveBeenCalled();
});

it("keeps review playback and seeking available but forbids edits", () => {
  const { changed } = mount({ readOnly: true });
  const editor = screen.getByRole("region", { name: "Audio/video segments" });
  fireEvent.keyDown(editor, { key: "t" });
  fireEvent.keyDown(editor, { key: "." });
  expect(changed).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "Add 1000ms segment (T)" }),
  ).toBeDisabled();
});
