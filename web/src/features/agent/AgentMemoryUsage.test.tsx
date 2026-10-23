import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { memory } from "../../test/memoryFixtures";

import { AgentMemoryUsage } from "./AgentMemoryUsage";

it("resolves used IDs to current memories and marks hard-deleted references", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([memory])))),
  );
  render(<AgentMemoryUsage ids={[memory.id, "deleted-id"]} />);
  expect(await screen.findByText(memory.content)).toBeVisible();
  expect(screen.getByText("Deleted memory (deleted-id)")).toBeVisible();
  expect(screen.getByRole("link", { name: "Manage memories" })).toHaveAttribute(
    "href",
    "#/memory",
  );
});
it("does not request memory or render an empty segment when none was used", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  const { container } = render(<AgentMemoryUsage ids={[]} />);
  expect(container).toBeEmptyDOMElement();
  expect(fetch).not.toHaveBeenCalled();
});
