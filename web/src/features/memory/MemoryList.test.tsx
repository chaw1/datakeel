import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { memory } from "../../test/memoryFixtures";

import { MemoryList } from "./MemoryList";

it("disables editing while saving and preserves the draft after an API error", async () => {
  let respond: (response: Response) => void = () => undefined;
  const fetch = vi.fn(
    () =>
      new Promise<Response>((resolve) => {
        respond = resolve;
      }),
  );
  vi.stubGlobal("fetch", fetch);
  const changed = vi.fn();
  const user = userEvent.setup();
  render(
    <MemoryList
      entries={[{ ...memory, id: "memory/a b" }]}
      datasets={[]}
      onDeleted={changed}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Edit memory" }));
  const editor = screen.getByRole("textbox", { name: "Edit memory content" });
  await user.clear(editor);
  await user.type(editor, "Revised v2 guidance");
  await user.click(screen.getByRole("button", { name: "Save memory" }));
  expect(editor).toBeDisabled();
  expect(screen.getByRole("button", { name: "Saving memory…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Cancel edit" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Delete memory" })).toBeDisabled();
  expect(fetch).toHaveBeenCalledWith(
    "/api/agent/memories/memory%2Fa%20b",
    expect.objectContaining({ method: "PATCH" }),
  );
  await act(() => {
    respond(
      new Response(JSON.stringify({ detail: "Memory unavailable" }), {
        status: 403,
      }),
    );
    return Promise.resolve();
  });
  expect(screen.getByRole("alert")).toHaveTextContent("403 Memory unavailable");
  expect(editor).toBeEnabled();
  expect(editor).toHaveValue("Revised v2 guidance");
  expect(screen.getByRole("button", { name: "Save memory" })).toBeEnabled();
  expect(changed).not.toHaveBeenCalled();
});
