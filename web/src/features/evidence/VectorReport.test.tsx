import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { vectorResult } from "../../test/vectorFixtures";

import { VectorReport } from "./VectorReport";

it("shows partial denominators, fake cost and unknown usage reservation", () => {
  render(<VectorReport result={vectorResult} />);
  expect(screen.getByText("3 / 2 / 1 / 0")).toBeVisible();
  expect(screen.getByText(/Real spend: 0 CNY/)).toBeVisible();
  expect(screen.getByText(/Fake requests \/ tokens \/ cost/)).toBeVisible();
  expect(screen.getByText(/UNKNOWN/)).toHaveTextContent(
    "Unknown / retained worst reservation",
  );
  expect(screen.getByText(/we-e1-v1/)).toBeInTheDocument();
});

it("renders cloud metered usage, cache hits and provider response IDs in real mode", () => {
  render(
    <VectorReport
      result={{
        ...vectorResult,
        report: {
          mode: "real",
          status: "success",
          nodes: [
            {
              mode: "real",
              fake_version: "we-cloud-http-v1",
              real_quality: "not_tested",
              status: "success",
              counts: { input: 4, eligible: 4, failed: 0, truncated: 0 },
              cache_hits: 1,
              fake_requests: 0,
              fake_usage: 0,
              fake_cost_nanos: 0,
              real_requests: 3,
              real_usage: 120,
              real_cost_nanos: 12_000_000,
            },
          ],
          attempts: [
            {
              id: "attempt-cloud-1",
              state: "SETTLED",
              usage: 40,
              token_bound: 60,
              reserved_nanos: 6_000_000,
              response_id: "req_cloud_001",
            },
          ],
        },
      }}
    />,
  );
  expect(screen.getByText(/Cloud HTTP embedding evidence/)).toBeVisible();
  expect(screen.queryByText(/Real spend: 0 CNY/)).not.toBeInTheDocument();
  expect(screen.getByText("Cloud requests / tokens / cost")).toBeVisible();
  expect(screen.getByText("3 / 120 / 0.012 CNY")).toBeVisible();
  expect(screen.getByText(/we-cloud-http-v1/)).toBeVisible();
  expect(screen.getByText("req_cloud_001")).toBeInTheDocument();
});
