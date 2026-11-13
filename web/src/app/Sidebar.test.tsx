import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { version } from "../../package.json";
import { I18nContext, translator } from "../i18n/context";

import { Sidebar } from "./Sidebar";

it.each(["en", "zh"] as const)(
  "shows only the package version in the %s sidebar",
  (locale) => {
    const { container } = render(
      <I18nContext.Provider
        value={{ locale, setLocale: () => undefined, t: translator(locale) }}
      >
        <Sidebar page="workbench" datasets={[]} error="" />
      </I18nContext.Provider>,
    );
    expect(screen.getByText(`v${version}`, { exact: true })).toBeVisible();
    expect(container.textContent).not.toMatch(/\bP\d+(?:\.\d+)?\b/);
  },
);

it("toggles the sidebar rail and collapses/expands navigation groups", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <I18nContext.Provider
      value={{ locale: "en", setLocale: () => undefined, t: translator("en") }}
    >
      <Sidebar page="workbench" datasets={[]} error="" />
    </I18nContext.Provider>,
  );

  const railToggle = screen.getByRole("button", { name: "Collapse sidebar" });
  expect(railToggle).toHaveAttribute("aria-expanded", "true");
  await user.click(railToggle);
  expect(container.querySelector(".sidebar")).toHaveAttribute(
    "data-collapsed",
    "true",
  );
  expect(
    screen.getByRole("button", { name: "Expand sidebar" }),
  ).toHaveAttribute("aria-expanded", "false");
  await user.click(screen.getByRole("button", { name: "Expand sidebar" }));
  expect(container.querySelector(".sidebar")).not.toHaveAttribute(
    "data-collapsed",
  );

  const dataGroupToggle = screen.getByRole("button", { name: "Data" });
  expect(dataGroupToggle).toHaveAttribute("aria-expanded", "true");
  await user.click(dataGroupToggle);
  expect(dataGroupToggle).toHaveAttribute("aria-expanded", "false");
  expect(
    container.querySelector('[data-nav-group="dataGroup"] .nav-group-items'),
  ).toHaveAttribute("hidden");
  await user.click(dataGroupToggle);
  expect(dataGroupToggle).toHaveAttribute("aria-expanded", "true");
});
