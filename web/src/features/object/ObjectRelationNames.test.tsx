import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { metric } from "../catalog/fixtures";

import { ObjectRelations } from "./ObjectRelations";
import { objectData } from "./testFixtures";

it.each(["en", "zh"] as const)(
  "keeps the owner source record and relationship card aligned in %s",
  (locale) => {
    const owner = "自定义负责人";
    const english = "Custom owner";
    const ownerId = `owner/${owner}`;
    const { container } = render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <ObjectRelations
          target={{
            kind: "metric",
            id: metric.definition.id,
            relation: "owner",
          }}
          onOpen={vi.fn()}
          data={{
            ...objectData,
            metric: {
              ...metric,
              definition: { ...metric.definition, owner },
              owner_english_name: english,
            },
            graph: {
              ...objectData.graph,
              nodes: [
                {
                  id: ownerId,
                  asset_id: ownerId,
                  asset_type: "owner",
                  namespace: "default",
                  label: owner,
                  english_name: english,
                },
              ],
              edges: [],
            },
          }}
        />
      </I18nContext.Provider>,
    );
    const expected = locale === "en" ? english : owner;
    expect(
      container.querySelector("#object-section-owner p"),
    ).toHaveTextContent(expected);
    expect(
      screen.getByRole("button", {
        name: `${locale === "en" ? "Inspect" : "查看"} ${expected}`,
      }),
    ).toBeVisible();
  },
);

it("keeps the original owner name when the relationship has no English metadata", () => {
  const owner = "备用负责人";
  const { container } = render(
    <ObjectRelations
      target={{ kind: "metric", id: metric.definition.id, relation: "owner" }}
      onOpen={vi.fn()}
      data={{
        ...objectData,
        metric: {
          ...metric,
          definition: { ...metric.definition, owner },
        },
      }}
    />,
  );
  expect(container.querySelector("#object-section-owner p")).toHaveTextContent(
    owner,
  );
});
