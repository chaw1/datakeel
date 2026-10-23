import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { StateBadge } from "./StateBadge";

it.each([
  ["en", "DENIED", "Denied", "red"],
  ["zh", "DENIED", "拒绝执行", "red"],
  ["en", "SUCCEEDED", "Succeeded", "green"],
] as const)(
  "shows a localized %s %s badge with the outcome color",
  (locale, state, label, color) => {
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: () => undefined, t: translator(locale) }}
      >
        <StateBadge state={state} />
      </I18nContext.Provider>,
    );
    expect(screen.getByText(label)).toHaveClass("badge", color);
  },
);
