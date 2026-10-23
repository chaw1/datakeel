import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { MessageComposer } from "./MessageComposer";

it("keeps a supplied draft until the user explicitly sends it", async () => {
  const onSend = vi.fn();
  render(
    <MessageComposer
      disabled={false}
      busy={false}
      initialContent="Inspect this dataset"
      onSend={onSend}
    />,
  );
  expect(screen.getByRole("textbox")).toHaveValue("Inspect this dataset");
  expect(onSend).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(onSend).toHaveBeenCalledExactlyOnceWith("Inspect this dataset");
  expect(screen.getByRole("textbox")).toHaveValue("");
});

it("does not submit while composition is active", () => {
  const onSend = vi.fn();
  render(
    <MessageComposer
      disabled={false}
      busy={false}
      initialContent="检查数据"
      onSend={onSend}
    />,
  );
  const input = screen.getByRole("textbox");
  const form = input.closest("form");
  if (!form) throw new Error("Missing form");
  fireEvent.compositionStart(input);
  fireEvent.submit(form);
  expect(onSend).not.toHaveBeenCalled();
  expect(input).toHaveValue("检查数据");
  fireEvent.compositionEnd(input);
  fireEvent.submit(form);
  expect(onSend).toHaveBeenCalledExactlyOnceWith("检查数据");
});

it("cancels native composing Enter on the draft and send button", () => {
  const onSend = vi.fn();
  render(
    <MessageComposer
      disabled={false}
      busy={false}
      initialContent="检查"
      onSend={onSend}
    />,
  );
  for (const target of [
    screen.getByRole("textbox"),
    screen.getByRole("button"),
  ]) {
    expect(fireEvent.keyDown(target, { key: "Enter", isComposing: true })).toBe(
      false,
    );
  }
  expect(onSend).not.toHaveBeenCalled();
});
