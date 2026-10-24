import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { kgRun } from "../../test/kgFixtures";

import { KGReports } from "./KGReports";

it("shows excluded entity names and types alongside relation proposal samples", () => {
  const report = kgRun.report;
  if (!report) throw new Error("Expected fixture report");
  const run = {
    ...kgRun,
    report: {
      ...report,
      proposals: [
        {
          reason: "unknown_entity_type" as const,
          count: 2,
          entity_samples: [{ name: "Acme", type: "company" }],
          samples: [
            {
              head: "Acme",
              relation: "uses",
              tail: "Widget",
              evidence: "Acme uses Widget.",
            },
          ],
        },
      ],
    },
  };
  render(<KGReports runs={[run]} proposalsOnly />);
  expect(screen.getByText("Acme · company")).toBeInTheDocument();
  expect(screen.getByText("Acme uses Widget.")).toBeInTheDocument();
});
