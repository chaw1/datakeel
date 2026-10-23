import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { report } from "../../test/fixtures";

import { ReportView } from "./ReportView";
it("renders a complete baseline report when enrichment is unavailable", () => {
  render(<ReportView report={report} />);
  expect(screen.getByText("A synthetic sample dataset.")).toBeVisible();
  expect(screen.getByText("Baseline fallback")).toBeVisible();
});
