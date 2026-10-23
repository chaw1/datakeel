import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { MemoryForm } from "./MemoryForm";

it("rejects empty memory and preserves content when saving fails", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(JSON.stringify({ detail: "Invalid memory" }), {
          status: 422,
        }),
      ),
    ),
  );
  render(<MemoryForm datasets={[]} onSaved={vi.fn()} />);
  const button = screen.getByRole("button", { name: "Add memory" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByRole("textbox"), "Useful reminder");
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid memory");
  expect(screen.getByRole("textbox")).toHaveValue("Useful reminder");
});
