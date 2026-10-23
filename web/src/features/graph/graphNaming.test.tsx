import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { useI18n } from "../../i18n/useI18n";
import { graph } from "../../test/fixtures";

import { RelationGraph } from "./RelationGraph";

import type { GraphNode } from "../../api/types";

const namedNodes: GraphNode[] = [
  {
    ...graph.nodes[0],
    id: "file",
    asset_type: "file",
    display_name: "val/scene-0817/image.png",
  },
  {
    ...graph.nodes[0],
    id: "metric",
    asset_type: "metric",
    display_name: "零售额",
  },
  {
    ...graph.nodes[0],
    id: "orders-date",
    asset_type: "column",
    display_name: "orders.date",
  },
  {
    ...graph.nodes[0],
    id: "sales-date",
    asset_type: "column",
    display_name: "sales.date",
  },
  {
    ...graph.nodes[0],
    id: "task",
    asset_type: "task",
    display_name: "Pipeline run",
  },
  {
    ...graph.nodes[0],
    id: "term",
    asset_type: "term",
    display_name: "term/零售额",
  },
];

function LocaleSwitch() {
  const { locale, setLocale, t } = useI18n();
  return (
    <button
      aria-label={t("language")}
      onClick={() => {
        setLocale(locale === "en" ? "zh" : "en");
      }}
    />
  );
}

it("renders readable cards, table prefixes and localized task labels as the language changes", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  const { container } = render(
    <I18nProvider>
      <LocaleSwitch />
      <RelationGraph graph={{ ...graph, nodes: namedNodes, edges: [] }} />
    </I18nProvider>,
  );
  const names = () =>
    [...container.querySelectorAll(".archive-name")].map(
      (node) => node.textContent,
    );
  expect(names()).toEqual(
    expect.arrayContaining([
      "scene-0817/image.png",
      "零售额",
      "orders.date",
      "sales.date",
      "流水线运行",
    ]),
  );
  expect(names().some((name) => name.includes("term/"))).toBe(false);
  expect(container.querySelector(".archive-prefix")).toHaveTextContent(
    "scene-0817/",
  );
  expect(
    [...container.querySelectorAll(".archive-prefix")].map(
      (node) => node.textContent,
    ),
  ).toEqual(expect.arrayContaining(["orders.", "sales."]));
  expect(
    [...container.querySelectorAll(".graph-column-title")].map(
      (node) => node.textContent,
    ),
  ).toContain("任务");
  expect(container).not.toHaveTextContent("Pipeline run");
  await userEvent.click(screen.getByRole("button", { name: "语言" }));
  expect(names()).toContain("Retail revenue");
  expect(names()).toContain("Pipeline run");
});

it.each([
  ["zh", "2 个资产 · 1 条关系边"],
  ["en", "2 assets · 1 edge"],
] as const)(
  "uses one count separator and correct count labels in %s",
  (locale, expected) => {
    localStorage.setItem("datakeel.locale", locale);
    const { container } = render(
      <I18nProvider>
        <RelationGraph graph={graph} />
      </I18nProvider>,
    );
    expect(container.querySelector(".graph-counts")).toHaveTextContent(
      expected,
    );
    expect(
      container.querySelector(".graph-counts")?.textContent.match(/·/g),
    ).toHaveLength(1);
  },
);
