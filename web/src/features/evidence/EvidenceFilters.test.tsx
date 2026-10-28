import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";

import { EvidenceFilters } from "./EvidenceFilters";
import { evidenceQuery, initialFilters } from "./query";

import type { EvidenceFilters as Filters } from "./query";
import type { Locale } from "../../i18n/context";

it.each([
  ["en", "Test", "Evidence filters", "Sample split", "Near duplicate in"],
  ["zh", "测试集", "证据筛选", "样本划分", "近重复所在集合"],
] as const)(
  "selects and submits test-set evidence filters in %s",
  async (locale, testName, panelName, splitName, nearName) => {
    const user = userEvent.setup();
    const changed = vi.fn<(value: Filters) => void>();
    function controls(value: Filters, language: Locale) {
      return (
        <I18nContext.Provider
          value={{
            locale: language,
            setLocale: vi.fn(),
            t: translator(language),
          }}
        >
          <EvidenceFilters value={value} onChange={changed} />
        </I18nContext.Provider>
      );
    }
    const { rerender } = render(controls(initialFilters, locale));
    await user.click(screen.getByText(panelName));
    const split = screen.getByLabelText(splitName);
    expect(within(split).getByRole("option", { name: testName })).toHaveValue(
      "test",
    );
    await user.selectOptions(split, "test");
    expect(changed).toHaveBeenLastCalledWith({
      ...initialFilters,
      split: "test",
    });
    const value = { ...initialFilters, split: "test" } satisfies Filters;
    rerender(controls(value, locale));
    const near = screen.getByLabelText(nearName);
    expect(within(near).getByRole("option", { name: testName })).toHaveValue(
      "test",
    );
    await user.selectOptions(near, "test");
    expect(changed).toHaveBeenLastCalledWith({ ...value, near: "test" });
    expect(
      evidenceQuery("dataset", { ...value, near: "test" }, null),
    ).toMatchObject({ split: "test", has_near_duplicate_in: "test" });
  },
);
