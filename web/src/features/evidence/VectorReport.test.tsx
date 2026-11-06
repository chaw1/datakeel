import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { vectorResult } from "../../test/vectorFixtures";

import { VectorReport } from "./VectorReport";

it("shows partial denominators, fake cost and unknown usage reservation", () => {
  render(<VectorReport result={vectorResult} />);
  expect(screen.getByText("3 / 2 / 1 / 0")).toBeVisible();
  expect(screen.getByText(/Real spend: 0 CNY/)).toBeVisible();
  expect(screen.getByText(/UNKNOWN/)).toHaveTextContent(
    "Unknown / retained worst reservation",
  );
  expect(screen.getByText(/we-e1-v1/)).toBeInTheDocument();
});
