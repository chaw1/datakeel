import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

import { objectKinds } from "../features/object/navigation";
import { I18nContext, translator } from "../i18n/context";

import { CommandPalette } from "./CommandPalette";

import type { components } from "../api/generated";

type SearchResult = components["schemas"]["SearchResult"];
const results: SearchResult[] = objectKinds.map((kind, index) => ({
  kind,
  id: `${kind}/object-${String(index)}`,
  name: `${kind} result`,
  ...(kind === "file" || kind === "version"
    ? { dataset_id: "dataset-context", version_id: "version-context" }
    : {}),
}));

beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(results)))),
  );
});

it.each(results)(
  "opens the $kind result using its canonical object route and source context",
  async (item) => {
    const user = userEvent.setup();
    const navigate = vi.fn();
    render(<CommandPalette onNavigate={navigate} />);
    await user.click(screen.getByRole("button", { name: "Search objects" }));
    expect(await screen.findAllByRole("option")).toHaveLength(8);
    await user.click(
      screen.getByRole("option", { name: new RegExp(item.name) }),
    );
    const query = new URLSearchParams({ tab: "relations" });
    if (item.dataset_id) query.set("dataset", item.dataset_id);
    if (item.version_id) query.set("version", item.version_id);
    expect(navigate).toHaveBeenCalledWith(
      `#/object/${item.kind}/${encodeURIComponent(item.id)}?${query.toString()}`,
    );
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith(
      "/api/search?q=&limit=40",
      expect.objectContaining({ method: "GET" }),
    );
  },
);

it("opens with Cmd or Ctrl K, moves selection in both directions, opens with Enter and closes with Escape", async () => {
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  fireEvent.keyDown(window, { key: "k", metaKey: true });
  await screen.findAllByRole("option");
  const input = screen.getByRole("combobox");
  expect(input).toHaveFocus();
  expect(input).toHaveAttribute("maxlength", "200");
  fireEvent.keyDown(input, { key: "ArrowUp" });
  expect(input).toHaveAttribute("aria-activedescendant", "command-option-7");
  fireEvent.keyDown(input, { key: "ArrowDown" });
  expect(input).toHaveAttribute("aria-activedescendant", "command-option-0");
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(navigate).toHaveBeenCalledWith(
    "#/object/file/file%2Fobject-1?tab=relations&dataset=dataset-context&version=version-context",
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  fireEvent.keyDown(window, { key: "K", ctrlKey: true });
  await screen.findAllByRole("option");
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "Escape" });
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(navigate).toHaveBeenCalledTimes(1);
});

it.each(["events", "native"] as const)(
  "blocks navigation, shortcuts and closing during %s composition",
  async (mode) => {
    const navigate = vi.fn();
    render(<CommandPalette onNavigate={navigate} />);
    const composing = mode === "native" ? { isComposing: true } : {};
    if (mode === "events") fireEvent.compositionStart(document);
    fireEvent.keyDown(window, { key: "k", metaKey: true, ...composing });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    if (mode === "events") fireEvent.compositionEnd(document);
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    await screen.findAllByRole("option");
    const input = screen.getByRole("combobox");
    if (mode === "events") fireEvent.compositionStart(input);
    for (const key of ["ArrowDown", "Enter", "Escape"])
      fireEvent.keyDown(input, { key, ...composing });
    fireEvent.keyDown(input, { key: "k", metaKey: true, ...composing });
    fireEvent.keyDown(input, { key: "k", ctrlKey: true, ...composing });
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(input).toHaveAttribute("aria-activedescendant", "command-option-0");
    expect(navigate).not.toHaveBeenCalled();
    if (mode === "events") fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(navigate).toHaveBeenCalledTimes(1);
  },
);

it("starts a conversation with only prompt and dataset navigation and never posts an action", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn<
    (path: string, options: RequestInit) => Promise<Response>
  >(() => Promise.resolve(new Response(JSON.stringify([results[1]]))));
  vi.stubGlobal("fetch", fetch);
  const navigate = vi.fn<(href: string) => void>();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await user.click(
    await screen.findByRole("button", {
      name: "Start a conversation about file result",
    }),
  );
  const href = navigate.mock.calls[0][0];
  expect(href.startsWith("#/agent?")).toBe(true);
  const query = new URLSearchParams(href.split("?")[1]);
  expect([...query.keys()].sort()).toEqual(["dataset", "prompt"]);
  expect(query.get("dataset")).toBe("dataset-context");
  expect(query.get("prompt")).toContain("file result");
  expect(query.get("prompt")).toContain("file/object-1");
  expect(
    fetch.mock.calls.every(([, options]) => options.method === "GET"),
  ).toBe(true);
});

it("reads the typed search term and exposes a retry without changing location on failure", async () => {
  const user = userEvent.setup();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(results)))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Search unavailable" }), {
        status: 503,
      }),
    )
    .mockResolvedValueOnce(new Response(JSON.stringify([results[0]])));
  vi.stubGlobal("fetch", fetch);
  const navigate = vi.fn();
  render(<CommandPalette onNavigate={navigate} />);
  await user.click(screen.getByRole("button", { name: "Search objects" }));
  await screen.findAllByRole("option");
  fireEvent.change(screen.getByRole("combobox"), { target: { value: "数据" } });
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Search unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(screen.getAllByRole("option")).toHaveLength(1);
  });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/search?q=%E6%95%B0%E6%8D%AE&limit=40",
    expect.objectContaining({ method: "GET" }),
  );
  expect(navigate).not.toHaveBeenCalled();
});

it("updates result and conversation names with the language while retaining IDs and original names", async () => {
  const items: SearchResult[] = [
    { kind: "metric", id: "retail_revenue", name: "零售额" },
    { kind: "term", id: "term/retail", name: "零售区域" },
    { kind: "table", id: "custom-table", name: "自定义表" },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(items)))),
  );
  const navigate = vi.fn<(href: string) => void>();
  const user = userEvent.setup();
  const content = (locale: "en" | "zh") => (
    <I18nContext.Provider
      value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
    >
      <CommandPalette onNavigate={navigate} />
    </I18nContext.Provider>
  );
  const { rerender } = render(content("en"));
  fireEvent.keyDown(window, { key: "k", metaKey: true });
  expect(
    await screen.findByRole("option", { name: /Retail revenue/ }),
  ).toBeVisible();
  expect(screen.getByRole("option", { name: /Retail region/ })).toBeVisible();
  expect(screen.getByRole("option", { name: /自定义表/ })).toBeVisible();
  rerender(content("zh"));
  expect(screen.getByRole("option", { name: /零售额/ })).toBeVisible();
  expect(screen.getByRole("option", { name: /零售区域/ })).toBeVisible();
  rerender(content("en"));
  await user.click(
    screen.getByRole("button", {
      name: "Start a conversation about Retail revenue",
    }),
  );
  const query = new URLSearchParams(navigate.mock.calls[0][0].split("?")[1]);
  expect(query.get("prompt")).toContain("Retail revenue");
  expect(query.get("prompt")).toContain("retail_revenue");
  expect(items[0].name).toBe("零售额");
});

it.each([
  ["dataset", "零售额", "en", "零售额"],
  ["file", "零售额", "en", "零售额"],
  ["metric", "Retail revenue", "zh", "Retail revenue"],
  ["term", "Retail region", "zh", "Retail region"],
  ["column", "orders.零售品类", "en", "orders.Retail category"],
  ["column", "orders.零售品类", "zh", "orders.零售品类"],
] as const)(
  "shows %s search name %s in %s without changing its identity",
  async (kind, name, locale, expected) => {
    const item: SearchResult = { kind, id: "original-object", name };
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify([item])))),
    );
    const navigate = vi.fn();
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <CommandPalette onNavigate={navigate} />
      </I18nContext.Provider>,
    );
    fireEvent.keyDown(window, { key: "k", metaKey: true });
    const result = await screen.findByRole("option");
    expect(result.querySelector(".command-name")).toHaveTextContent(expected);
    await userEvent.click(result);
    expect(navigate).toHaveBeenCalledWith(
      `#/object/${kind}/original-object?tab=relations`,
    );
  },
);
