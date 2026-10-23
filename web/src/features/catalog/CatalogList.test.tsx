import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { CatalogList } from "./CatalogList";
import { page, source } from "./fixtures";

it("paginates the actual total and resets the offset for a new search", async () => {
  const fetch = vi.fn((input: string) => {
    const offset = Number(
      new URL(input, "http://localhost").searchParams.get("offset"),
    );
    return Promise.resolve(
      new Response(JSON.stringify(page([source], 21, offset))),
    );
  });
  vi.stubGlobal("fetch", fetch);
  const select = vi.fn();
  const user = userEvent.setup();
  render(
    <CatalogList collection="sources" label="Data sources" onSelect={select} />,
  );
  await user.click(
    await screen.findByRole("button", { name: /Fictional Kitchen Ecommerce/ }),
  );
  expect(select).toHaveBeenCalledWith(source);
  await user.click(screen.getByRole("button", { name: "Next" }));
  expect(await screen.findByText("21–21 of 21")).toBeVisible();
  expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  await user.type(screen.getByRole("searchbox"), "retail");
  await waitFor(() => {
    expect(fetch).toHaveBeenLastCalledWith(
      expect.stringContaining("offset=0&search=retail"),
      expect.any(Object),
    );
  });
});

it("shows errors with a retry and reports a successful empty result separately", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Offline" }), { status: 500 }),
    )
    .mockResolvedValue(new Response(JSON.stringify(page([]))));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <CatalogList
      collection="sources"
      label="Data sources"
      onSelect={vi.fn()}
    />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Offline");
  expect(
    screen.queryByText("No registered objects match this view."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(
    await screen.findByText("No registered objects match this view."),
  ).toBeVisible();
});

it("preserves an original English catalog name in the Chinese interface", async () => {
  const item = { ...source, name: "Retail revenue" };
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(page([item]))))),
  );
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <CatalogList collection="sources" label="Sources" onSelect={vi.fn()} />
    </I18nContext.Provider>,
  );
  expect(
    await screen.findByRole("button", { name: /Retail revenue/ }),
  ).toBeVisible();
  expect(screen.queryByText("零售额")).not.toBeInTheDocument();
});
