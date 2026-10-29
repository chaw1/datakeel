import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { splitSet } from "./testFixtures";
import { TrainingWorkspace } from "./TrainingWorkspace";

it.each([
  {
    locale: "en",
    sourceName: "Split source",
    savedName: "Saved split set",
  },
  {
    locale: "zh",
    sourceName: "切分来源",
    savedName: "已保存的切分集合",
  },
])(
  "gives both training selectors explicit $locale aria labels",
  async ({ locale, sourceName, savedName }) => {
    localStorage.setItem("datakeel.locale", locale);
    vi.stubGlobal(
      "fetch",
      vi.fn(() => Promise.resolve(new Response(JSON.stringify([splitSet])))),
    );
    render(
      <I18nProvider>
        <TrainingWorkspace datasetId="dataset-1" versionId="version-1" />
      </I18nProvider>,
    );
    expect(screen.getByRole("combobox", { name: sourceName })).toHaveAttribute(
      "aria-label",
      sourceName,
    );
    expect(
      await screen.findByRole("combobox", { name: savedName }),
    ).toHaveAttribute("aria-label", savedName);
  },
);
