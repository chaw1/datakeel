import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

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
    expect(
      screen.getByRole("rowheader", { name: "total" }),
    ).toBeVisible();
    expect(error).not.toHaveBeenCalled();
  } finally {
    error.mockRestore();
  }
});
