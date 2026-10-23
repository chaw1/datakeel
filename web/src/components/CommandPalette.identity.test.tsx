import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { CommandPalette } from "./CommandPalette";

import type { components } from "../api/generated";

type SearchResult = components["schemas"]["SearchResult"];
const file: SearchResult = {
  kind: "file",
  id: "1234abcd-5678-4abc-9876-0123456789ab",
  name: "val/scene-0817/image.png",
  dataset_id: "dataset-parent",
  version_id: "version-source",
};
const href =
  "#/object/file/1234abcd-5678-4abc-9876-0123456789ab?tab=relations&dataset=dataset-parent&version=version-source";

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

function paste(value: string) {
  fireEvent.paste(screen.getByRole("combobox"), {
    clipboardData: { getData: () => value },
  });
}

it.each([file.id, file.id.slice(0, 8), file.id.slice(0, 8).toUpperCase()])(
  "pasting unique identity %s opens its object with source context",
  async (value) => {
    const user = userEvent.setup();
    const fetch = vi.fn<(path: string, init: RequestInit) => Promise<Response>>(
      () => Promise.resolve(new Response(JSON.stringify([file]))),
    );
    vi.stubGlobal("fetch", fetch);
    const navigate = vi.fn();
    render(<CommandPalette onNavigate={navigate} />);
    await user.click(screen.getByRole("button", { name: "Search objects" }));
    await screen.findByRole("option");
    paste(value);
    await waitFor(() => {
      expect(navigate).toHaveBeenCalledWith(href);
    });
    expect(fetch).toHaveBeenCalledWith(
      `/api/search?${new URLSearchParams({ q: value, limit: "100" }).toString()}`,
      expect.objectContaining({ method: "GET" }),
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch.mock.calls.every(([, init]) => init.method === "GET")).toBe(
      true,
    );
  },
);

it("keeps ambiguous prefixes in the palette until an explicit choice", async () => {
  const user = userEvent.setup();
  const second = {
    ...file,
    id: "1234abcd-1111-4abc-9876-0123456789ab",
    name: "another.png",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify([file, second])))),
  );
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await screen.findAllByRole("option");
  paste("1234abcd");
  await waitFor(() => {
    expect(screen.getAllByRole("option")).toHaveLength(2);
  });
  expect(screen.getByRole("combobox")).toHaveValue("1234abcd");
  expect(navigate).not.toHaveBeenCalled();
  await user.click(screen.getByRole("option", { name: /another.png/ }));
  expect(navigate).toHaveBeenCalledWith(expect.stringContaining(second.id));
});

it("does not navigate for a name match that is not an identity prefix", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify([
            {
              ...file,
              id: "9999abcd-5678-4abc-9876-0123456789ab",
              name: "1234abcd.txt",
            },
          ]),
        ),
      ),
    ),
  );
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await screen.findByRole("option");
  paste("1234abcd");
  expect(
    await screen.findByRole("option", { name: /1234abcd.txt/ }),
  ).toBeVisible();
  expect(navigate).not.toHaveBeenCalled();
});

it("ignores a delayed paste lookup after the palette closes", async () => {
  const user = userEvent.setup();
  let finish: (response: Response) => void = () => undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      path.includes("limit=100")
        ? new Promise<Response>((resolve) => {
            finish = resolve;
          })
        : Promise.resolve(new Response(JSON.stringify([file]))),
    ),
  );
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await screen.findByRole("option");
  paste("1234abcd");
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await act(async () => {
    finish(new Response(JSON.stringify([file])));
    await Promise.resolve();
  });
  expect(navigate).not.toHaveBeenCalled();
});

it("does not perform the special paste lookup during composition", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify([file]))),
  );
  vi.stubGlobal("fetch", fetch);
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await screen.findByRole("option");
  fireEvent.compositionStart(screen.getByRole("combobox"));
  paste("1234abcd");
  expect(fetch).toHaveBeenCalledTimes(1);
  expect(navigate).not.toHaveBeenCalled();
  fireEvent.compositionEnd(screen.getByRole("combobox"));
});
