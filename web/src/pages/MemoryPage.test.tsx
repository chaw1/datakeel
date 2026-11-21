import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n/I18nProvider";
import { dataset } from "../test/fixtures";
import { memory } from "../test/memoryFixtures";

import { MemoryPage } from "./MemoryPage";

import type { MemoryEntry } from "../api/types";

function mockApi() {
  let entries: MemoryEntry[] = [
    memory,
    {
      ...memory,
      id: "memory-2",
      dataset_id: dataset.id,
      content: "Dataset-specific note",
    },
  ];
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      const body = JSON.parse(
        typeof init.body === "string" ? init.body : "{}",
      ) as {
        content: string;
        dataset_id: string | null;
      };
      const item = {
        ...memory,
        ...body,
        id: "memory-added",
        source_conversation_ids: [],
      };
      entries.push(item);
      return Promise.resolve(new Response(JSON.stringify(item)));
    }
    if (init?.method === "DELETE") {
      entries = entries.filter((entry) => !path.endsWith(entry.id));
      return Promise.resolve(
        new Response(JSON.stringify({ deleted_ids: ["memory-1"] })),
      );
    }
    if (init?.method === "PATCH") {
      entries = entries.map((entry) =>
        path.endsWith(entry.id)
          ? { ...entry, content: "Contact [REDACTED]" }
          : entry,
      );
      return Promise.resolve(new Response(JSON.stringify(entries[0])));
    }
    const query = new URL(path, "http://localhost").searchParams.get("q");
    return Promise.resolve(
      new Response(
        JSON.stringify(
          query
            ? entries.filter((entry) =>
                entry.content.toLowerCase().includes(query.toLowerCase()),
              )
            : entries,
        ),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
it("shows source links and current strength, and filters exact dataset or global scopes", async () => {
  mockApi();
  const user = userEvent.setup();
  render(<MemoryPage datasets={[dataset]} />);
  expect(await screen.findByText(memory.content)).toBeVisible();
  expect(
    screen.getAllByRole("link", { name: "Conversation conversation-1" })[0],
  ).toHaveAttribute("href", "#/agent?conversation=conversation-1");
  expect(screen.getAllByText("0.98")).toHaveLength(2);
  const filter = screen.getByRole("combobox", {
    name: "Filter memory by dataset",
  });
  await user.selectOptions(filter, dataset.id);
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(screen.getByText("Dataset-specific note")).toBeVisible();
  await user.selectOptions(filter, "global");
  expect(screen.getByText(memory.content)).toBeVisible();
  expect(screen.queryByText("Dataset-specific note")).not.toBeInTheDocument();
});
it("adds typed scoped memory, cancels a deletion, then deletes only after confirmation", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  render(<MemoryPage datasets={[dataset]} />);
  await screen.findByText(memory.content);
  await user.type(
    screen.getByRole("textbox", { name: "Memory content" }),
    "Keep generated samples separate.",
  );
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Scope" }),
    dataset.id,
  );
  await user.click(screen.getByRole("button", { name: "Add memory" }));
  expect(
    await screen.findByText("Keep generated samples separate."),
  ).toBeVisible();
  const posted = fetch.mock.calls.find(
    ([, init]) => init?.method === "POST",
  )?.[1]?.body;
  expect(posted).toContain(`"dataset_id":"${dataset.id}"`);
  await user.click(screen.getAllByRole("button", { name: "Delete memory" })[0]);
  expect(
    fetch.mock.calls.filter(([, init]) => init?.method === "DELETE"),
  ).toHaveLength(0);
  await user.click(screen.getByRole("button", { name: "Keep memory" }));
  expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
  await user.click(screen.getAllByRole("button", { name: "Delete memory" })[0]);
  await user.click(
    within(screen.getByRole("alertdialog")).getByRole("button", {
      name: "Confirm deletion",
    }),
  );
  await waitFor(() => {
    expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  });
  expect(
    fetch.mock.calls.filter(([, init]) => init?.method === "DELETE"),
  ).toHaveLength(1);
});
it("renders the complete memory controls in Chinese", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  mockApi();
  render(
    <I18nProvider>
      <MemoryPage datasets={[dataset]} />
    </I18nProvider>,
  );
  expect(await screen.findByText(memory.content)).toBeVisible();
  expect(screen.getByRole("textbox", { name: "记忆内容" })).toBeVisible();
  expect(
    screen.getByRole("combobox", { name: "按数据集筛选记忆" }),
  ).toBeVisible();
  expect(screen.getAllByText("最近使用")).toHaveLength(2);
  expect(screen.getByRole("searchbox", { name: "搜索记忆" })).toBeVisible();
  expect(screen.getAllByRole("button", { name: "编辑记忆" })).toHaveLength(2);
});
it("keeps a failed deletion visible and reports the API error", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((_path: string, init?: RequestInit) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            init?.method === "DELETE"
              ? { detail: "Memory unavailable" }
              : [memory],
          ),
          { status: init?.method === "DELETE" ? 409 : 200 },
        ),
      ),
    ),
  );
  render(<MemoryPage datasets={[]} />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Delete memory" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Confirm deletion" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "409 Memory unavailable",
  );
  expect(screen.getByText(memory.content)).toBeVisible();
});

it("searches through the API and restores the scoped list after clearing", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  render(<MemoryPage datasets={[dataset]} />);
  await screen.findByText(memory.content);
  const search = screen.getByRole("searchbox", { name: "Search memories" });
  await user.type(search, "Dataset-specific");
  expect(await screen.findByText("Dataset-specific note")).toBeVisible();
  expect(screen.queryByText(memory.content)).not.toBeInTheDocument();
  expect(
    fetch.mock.calls.some(([path]) => path.endsWith("?q=Dataset-specific")),
  ).toBe(true);
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Filter memory by dataset" }),
    "global",
  );
  expect(screen.queryByText("Dataset-specific note")).not.toBeInTheDocument();
  await user.clear(search);
  expect(await screen.findByText(memory.content)).toBeVisible();
  expect(screen.queryByText("Dataset-specific note")).not.toBeInTheDocument();
});

it("ignores an older search response after the query changes", async () => {
  const pending = new Map<string, (response: Response) => void>();
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (path: string) =>
        new Promise<Response>((resolve) => {
          pending.set(path, resolve);
        }),
    ),
  );
  render(<MemoryPage datasets={[]} />);
  const search = screen.getByRole("searchbox", { name: "Search memories" });
  fireEvent.change(search, { target: { value: "v2" } });
  fireEvent.change(search, { target: { value: "qwen3.5" } });
  await act(() => {
    pending.get("/api/agent/memories?q=qwen3.5")?.(
      new Response(JSON.stringify([{ ...memory, content: "qwen3.5" }])),
    );
    return Promise.resolve();
  });
  expect(screen.getByText("qwen3.5")).toBeVisible();
  await act(() => {
    pending.get("/api/agent/memories?q=v2")?.(
      new Response(JSON.stringify([{ ...memory, content: "v2" }])),
    );
    return Promise.resolve();
  });
  expect(screen.getByText("qwen3.5")).toBeVisible();
  expect(screen.queryByText("v2")).not.toBeInTheDocument();
});

it("cancels inline edits and reloads server-redacted content after saving", async () => {
  const fetch = mockApi();
  const user = userEvent.setup();
  render(<MemoryPage datasets={[]} />);
  await screen.findByText(memory.content);
  await user.click(screen.getAllByRole("button", { name: "Edit memory" })[0]);
  await user.clear(
    screen.getByRole("textbox", { name: "Edit memory content" }),
  );
  expect(screen.getByRole("button", { name: "Save memory" })).toBeDisabled();
  await user.click(screen.getByRole("button", { name: "Cancel edit" }));
  expect(screen.getByText(memory.content)).toBeVisible();
  expect(fetch.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(
    false,
  );
  await user.click(screen.getAllByRole("button", { name: "Edit memory" })[0]);
  const editor = screen.getByRole("textbox", { name: "Edit memory content" });
  await user.clear(editor);
  await user.type(editor, "Contact person@example.com");
  await user.click(screen.getByRole("button", { name: "Save memory" }));
  expect(await screen.findByText("Contact [REDACTED]")).toBeVisible();
  expect(
    screen.queryByText("Contact person@example.com"),
  ).not.toBeInTheDocument();
  const patch = fetch.mock.calls.find(([, init]) => init?.method === "PATCH");
  expect(patch?.[0]).toBe(`/api/agent/memories/${memory.id}`);
  expect(patch?.[1]?.body).toBe(
    JSON.stringify({ content: "Contact person@example.com" }),
  );
  expect(screen.getAllByText("0.98")).toHaveLength(2);
});
