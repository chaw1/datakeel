import { render, screen } from "@testing-library/react";
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
