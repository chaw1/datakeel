import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { IntentCard } from "./IntentCard";

import type { IntentResult } from "../../api/intents";

const answer: IntentResult = {
  kind: "answer",
  text: "Li has the highest rework rate.",
  parser: "model",
  request: "",
  chain: null,
  clarification: null,
  answer: null,
  missing_scopes: [],
  draft: {},
};
const props = { busy: false, onResolved: vi.fn(), onOpenReceipt: vi.fn() };

it("marks every one-sentence result as a beta feature", () => {
  render(<IntentCard {...props} intent={answer} />);
  const badge = screen.getByText("Beta");
  expect(badge).toBeVisible();
  expect(badge).toHaveAttribute(
    "title",
    expect.stringContaining("eight in ten"),
  );
});

it("says 试用 with the Chinese note when the interface is Chinese", () => {
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <IntentCard {...props} intent={answer} />
    </I18nContext.Provider>,
  );
  expect(screen.getByText("试用")).toHaveAttribute(
    "title",
    expect.stringContaining("八成"),
  );
});
