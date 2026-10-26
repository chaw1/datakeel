import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { Topbar } from "../../app/Topbar";
import { I18nContext, translator } from "../../i18n/context";
import { actionPlan } from "../../test/actionFixtures";
import { ApprovalObjects } from "../approvals/ApprovalObjects";
import { safeNodeName } from "../graph/archiveModel";

import { ObjectHeader } from "./ObjectHeader";
import { objectData } from "./testFixtures";

import type { ObjectTarget } from "./navigation";
import type { Locale } from "../../i18n/context";

const names = [
  ["metric", "零售额", "Retail revenue"],
  ["term", "零售区域", "Retail region"],
  ["table", "销售额", "Sales amount"],
  ["column", "零售品类", "Retail category"],
  ["metric", "自定义毛利", "自定义毛利"],
  ["term", "Original name", "Original name"],
  ["column", "orders.零售品类", "orders.Retail category"],
  ["dataset", "零售额", "零售额"],
  ["file", "零售额", "零售额"],
  ["table", "Retail revenue", "Retail revenue"],
] as const;

it.each(names)(
  "keeps the %s title, breadcrumb and approval aligned with the graph for %s",
  (kind, name, english) => {
    const target: ObjectTarget = { kind, id: "named-object" };
    const node = {
      namespace: "default",
      asset_id: target.id,
      asset_type: kind,
      id: target.id,
      label: name,
    };
    const plan = {
      ...actionPlan,
      manifest: {
        ...actionPlan.manifest,
        objects: [
          {
            ...actionPlan.manifest.objects[0],
            asset_ref: node,
            properties: { name },
          },
        ],
      },
    };
    function content(locale: Locale) {
      return (
        <I18nContext.Provider
          value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
        >
          <Topbar
            page="object"
            navigate={vi.fn()}
            objectName={name}
            objectKind={kind}
          />
          <ObjectHeader
            data={{ ...objectData, name, target }}
            target={target}
          />
          <ApprovalObjects plan={plan} />
        </I18nContext.Provider>
      );
    }
    const { rerender } = render(content("en"));
    for (const [locale, expected] of [
      ["en", english],
      ["zh", name],
    ] as const) {
      rerender(content(locale));
      expect(
        screen.getByRole("heading", { level: 1, name: expected }),
      ).toBeVisible();
      expect(document.querySelector(".breadcrumb-current")).toHaveTextContent(
        locale === "en" ? expected : "对象",
      );
      expect(screen.getByRole("link", { name: expected })).toBeVisible();
      expect(safeNodeName(node, locale)).toBe(expected);
    }
    expect(plan.manifest.objects[0].properties.name).toBe(name);
  },
);

it("preserves an original English metric name in Chinese titles and generic approvals", () => {
  const name = "Retail revenue";
  const target: ObjectTarget = { kind: "metric", id: "retail_revenue" };
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <ObjectHeader data={{ ...objectData, name, target }} target={target} />
      <ApprovalObjects
        plan={{
          ...actionPlan,
          manifest: {
            ...actionPlan.manifest,
            objects: [
              {
                ...actionPlan.manifest.objects[0],
                asset_ref: {
                  namespace: "default",
                  asset_type: "metric",
                  asset_id: target.id,
                },
                properties: { name },
              },
            ],
          },
        }}
      />
    </I18nContext.Provider>,
  );
  expect(screen.getByRole("heading", { level: 1, name })).toBeVisible();
  expect(screen.getByRole("link", { name })).toBeVisible();
});

it.each(["source", "dimension", "owner"])(
  "localizes %s approval and graph names without requiring an object route",
  (kind) => {
    const node = {
      namespace: "default",
      asset_id: "related-object",
      asset_type: kind,
      id: "related-object",
      label: "零售区域",
    };
    render(
      <ApprovalObjects
        plan={{
          ...actionPlan,
          manifest: {
            ...actionPlan.manifest,
            objects: [
              {
                ...actionPlan.manifest.objects[0],
                asset_ref: node,
                properties: { name: node.label },
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText("Retail region")).toBeVisible();
    expect(safeNodeName(node, "en")).toBe("Retail region");
    expect(safeNodeName(node, "zh")).toBe(node.label);
  },
);

it("falls back to the identity when the object has no name", () => {
  const target: ObjectTarget = { kind: "metric", id: "unnamed-metric" };
  render(<ObjectHeader data={{ ...objectData, name: "" }} target={target} />);
  expect(
    screen.getByRole("heading", { level: 1, name: target.id }),
  ).toBeVisible();
});

it.each(["en", "zh"] as const)(
  "uses optional English object metadata while keeping a non-UUID ID complete in %s",
  (locale) => {
    const target: ObjectTarget = { kind: "metric", id: "retail_revenue" };
    const name = "自定义营业额";
    const englishName = "Custom turnover";
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <ObjectHeader
          data={{ ...objectData, name, englishName }}
          target={target}
        />
      </I18nContext.Provider>,
    );
    expect(
      screen.getByRole("heading", {
        level: 1,
        name: locale === "en" ? englishName : name,
      }),
    ).toBeVisible();
    expect(document.querySelector(".object-id code")).toHaveTextContent(
      /^retail_revenue$/,
    );
    const node = {
      namespace: "default",
      asset_id: target.id,
      asset_type: target.kind,
      id: target.id,
      label: name,
      english_name: englishName,
    };
    expect(safeNodeName(node, locale)).toBe(
      locale === "en" ? englishName : name,
    );
  },
);
