import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { splitSet } from "./testFixtures";
import { TrainingDistribution } from "./TrainingDistribution";

it("renders a class named total without colliding with the sample total row", () => {
  const error = vi.spyOn(console, "error");
  try {
    render(
      <TrainingDistribution
        split={{
          ...splitSet,
          distributions: [
            {
              split: "train",
              count: 1,
              labels: [{ label: "total", count: 1 }],
            },
          ],
        }}
      />,
    );
    expect(
      screen.getByRole("rowheader", { name: "All samples" }),
    ).toBeVisible();
    expect(screen.getByRole("rowheader", { name: "total" })).toBeVisible();
    expect(error).not.toHaveBeenCalled();
  } finally {
    error.mockRestore();
  }
});

it.each(["en", "zh"])(
  "explains generated 24/0/0 distributions in %s",
  (locale) => {
    localStorage.setItem("datakeel.locale", locale);
    render(
      <I18nProvider>
        <TrainingDistribution
          split={{
            ...splitSet,
            members: Array.from({ length: 24 }, (_, ordinal) => ({
              ...splitSet.members[0],
              sample_id: `demo-${String(ordinal)}`,
              split: "train" as const,
            })),
            distributions: [
              { split: "train", count: 24, labels: [] },
              { split: "val", count: 0, labels: [] },
              { split: "test", count: 0, labels: [] },
            ],
          }}
        />
      </I18nProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      locale === "zh"
        ? "显式分组和已启用的重复隔离约束"
        : "Explicit groups and duplicate constraints that are enabled",
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      locale === "zh"
        ? "当前结果不表示不存在其他切分"
        : "does not prove that no other split is possible",
    );
  },
);

it("does not warn about a deliberately disabled test set", () => {
  render(
    <TrainingDistribution
      split={{
        ...splitSet,
        request: {
          ...splitSet.request,
          ratios: { train: 0.8, val: 0.2, test: 0 },
        },
        distributions: [
          { split: "train", count: 2, labels: [] },
          { split: "val", count: 1, labels: [] },
          { split: "test", count: 0, labels: [] },
        ],
      }}
    />,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it("does not attribute imported empty directories to generated allocation", () => {
  render(
    <TrainingDistribution
      split={{
        ...splitSet,
        request: { ...splitSet.request, source: "directory" },
        distributions: [
          { split: "train", count: 3, labels: [] },
          { split: "val", count: 0, labels: [] },
          { split: "test", count: 0, labels: [] },
        ],
      }}
    />,
  );
  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});

it.each(["en", "zh"])(
  "qualifies duplicate constraints when avoidance is disabled in %s",
  (locale) => {
    localStorage.setItem("datakeel.locale", locale);
    render(
      <I18nProvider>
        <TrainingDistribution
          split={{
            ...splitSet,
            members: splitSet.members.slice(0, 1),
            request: { ...splitSet.request, avoid_leakage: false },
            distributions: [
              { split: "train", count: 1, labels: [] },
              { split: "val", count: 0, labels: [] },
              { split: "test", count: 0, labels: [] },
            ],
          }}
        />
      </I18nProvider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      locale === "zh"
        ? "已启用的重复隔离约束"
        : "duplicate constraints that are enabled",
    );
  },
);
