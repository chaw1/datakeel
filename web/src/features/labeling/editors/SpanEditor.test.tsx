import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { SpanEditor } from "./SpanEditor";

import type { AnnotationRecord, EditorProps } from "./types";

const labels = [
  { id: "cat", name: "Cat", shortcut: "1", attributes: {} },
  { id: "dog", name: "Dog", shortcut: "2", attributes: {} },
];
function mount(_kind: "text_span", options: Partial<EditorProps> = {}) {
  const changed = vi.fn<(value: AnnotationRecord) => void>();
  function Harness() {
    const [value, setValue] = useState<AnnotationRecord>({
      sample_id: "sample",
      annotator_id: "local",
    });
    return (
      <>
        <SpanEditor
          labels={labels}
          template={{
            id: "template",
            name: "Template",
            annotation_type: "text_span",
            revision: 1,
            archived: false,
            component_config: {},
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
  expect(
    screen.getByRole("button", { name: "Delete annotation" }),
  ).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: /^Cat · 2–4 · / }));
  fireEvent.click(screen.getByRole("button", { name: "Delete annotation" }));
  expect(annotation().spans).toEqual([
    { category: "cat", start: 1, end: 5, attributes: {} },
  ]);
});
it("adds nested spans from typed offsets without editing the span just added", () => {
  const { annotation } = mount("text_span", { text: "A😀中文 nested" });
  const start = screen.getByRole("spinbutton", { name: "Start character" });
  const end = screen.getByRole("spinbutton", {
    name: "End character (exclusive)",
  });
  const add = screen.getByRole("button", { name: "Label selection" });
  fireEvent.change(start, { target: { value: "0" } });
  fireEvent.change(end, { target: { value: "6" } });
  fireEvent.click(add);
  expect(screen.getByText(/describe a new selection/)).toBeVisible();
  fireEvent.change(start, { target: { value: "2" } });
  fireEvent.change(end, { target: { value: "4" } });
  fireEvent.click(add);
  expect(annotation().spans).toEqual([
    { category: "cat", start: 0, end: 6, attributes: {} },
    { category: "cat", start: 2, end: 4, attributes: {} },
  ]);
  // Choosing a span edits it until Escape returns the offsets to a new selection.
  fireEvent.click(screen.getByRole("button", { name: /^Cat · 0–6 · / }));
  expect(screen.getByText(/edit the selected span 0–6/)).toBeVisible();
  const editor = screen.getByRole("region", { name: "Text spans" });
  fireEvent.keyDown(editor, { key: "Escape" });
  fireEvent.change(start, { target: { value: "1" } });
  fireEvent.click(add);
  expect(annotation().spans?.map(({ start, end }) => [start, end])).toEqual([
    [0, 6],
    [2, 4],
    [1, 6],
  ]);
});
it("keeps typed offsets when focus passes through the source text", () => {
  const { annotation } = mount("text_span", { text: "猫 and dog" });
  const source = screen.getByRole("textbox", {
    name: "Source text: select a range, then press Enter",
  });
  if (!(source instanceof HTMLTextAreaElement))
    throw new Error("Source is not a textarea");
  source.setSelectionRange(0, 1);
  fireEvent.select(source);
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "Start character" }),
    {
      target: { value: "2" },
    },
  );
  fireEvent.change(
    screen.getByRole("spinbutton", { name: "End character (exclusive)" }),
    { target: { value: "5" } },
  );
  fireEvent.select(source);
  fireEvent.click(screen.getByRole("button", { name: "Label selection" }));
  expect(annotation().spans?.[0]).toMatchObject({ start: 2, end: 5 });
});
it("takes label shortcuts on the source text and the label list", () => {
  const { annotation } = mount("text_span", { text: "猫 and dog" });
  const source = screen.getByRole("textbox", {
    name: "Source text: select a range, then press Enter",
  });
  if (!(source instanceof HTMLTextAreaElement))
    throw new Error("Source is not a textarea");
  expect(source.readOnly).toBe(false);
  expect(source).toHaveAttribute("aria-readonly", "true");
  const typed = new Event("beforeinput", { bubbles: true, cancelable: true });
  source.dispatchEvent(typed);
  expect(typed.defaultPrevented).toBe(true);
  fireEvent.keyDown(source, { key: "2" });
  source.setSelectionRange(0, 1);
  fireEvent.select(source);
  fireEvent.keyDown(source, { key: "Enter" });
  expect(annotation().spans?.[0]).toMatchObject({ category: "dog", end: 1 });
  const picker = screen.getByRole("combobox", { name: "Label" });
  fireEvent.keyDown(picker, { key: "1" });
  expect(picker).toHaveValue("cat");
  fireEvent.click(screen.getByRole("button", { name: /^Dog · 0–1 · / }));
  fireEvent.keyDown(picker, { key: "1" });
  expect(annotation().spans?.[0]).toMatchObject({ category: "cat" });
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
