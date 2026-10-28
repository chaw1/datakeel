import { render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { column, table } from "../catalog/fixtures";

import { ObjectProfile } from "./ObjectProfile";
import { ObjectSections } from "./ObjectSections";
import { objectData } from "./testFixtures";

const profile = {
  name: "temperature",
  inferred_type: "number",
  null_rate: 0.125,
  unique_rate: 0.75,
  primary_key_candidate: false,
  pii_kinds: [],
  distribution: { numeric: { minimum: 12, maximum: 35 } },
};

it("shows readable table profile facts on the object facts tab", () => {
  render(
    <ObjectSections
      target={{ kind: "table", id: table.asset_ref.asset_id, tab: "facts" }}
      data={{
        ...objectData,
        catalog: {
          ...table,
          properties: {
            table_profile: {
              row_count: 8,
              columns: [profile],
              foreign_keys: [
                {
                  column: "device_id",
                  referenced_file: "devices.csv",
                  referenced_column: "id",
                  coverage: 1,
                },
              ],
            },
          },
        },
      }}
      reload={vi.fn()}
      onOpen={vi.fn()}
    />,
  );
  const region = screen.getByRole("region", { name: "Table profile" });
  expect(within(region).getByText("Rows analyzed: 8")).toBeVisible();
  const row = within(region).getByRole("row", { name: /temperature/ });
  expect(within(row).getByText("Number")).toBeVisible();
  expect(within(row).getByText("12.5%")).toBeVisible();
  expect(within(row).getByText("75.0%")).toBeVisible();
  expect(within(row).getByText("12 – 35")).toBeVisible();
  expect(
    within(region).getByText("Possible foreign keys (value coverage)"),
  ).toBeVisible();
  expect(
    within(region).getByText("device_id → devices.csv.id (100.0%)"),
  ).toBeInTheDocument();
});

it("shows column key and contact candidates without inventing source constraints", () => {
  render(
    <ObjectProfile
      object={{
        ...column,
        properties: {
          profile: {
            ...profile,
            name: "phone",
            inferred_type: "identifier",
            primary_key_candidate: true,
            pii_kinds: ["phone"],
            distribution: {
              numeric: null,
              top_values: [{ value: "[REDACTED]", count: 8 }],
            },
          },
        },
      }}
    />,
  );
  expect(screen.getByText("Possible primary key")).toBeVisible();
  expect(screen.getByText("Yes")).toBeVisible();
  expect(screen.getByText("Phone number")).toBeVisible();
  expect(screen.getByText("[REDACTED] (8)")).toBeVisible();
});

it("handles absent or malformed optional profiles without failing the object", () => {
  const { container, rerender } = render(<ObjectProfile object={undefined} />);
  expect(container).toBeEmptyDOMElement();
  rerender(
    <ObjectProfile object={{ ...table, properties: { table_profile: [] } }} />,
  );
  expect(container).toBeEmptyDOMElement();
  rerender(
    <ObjectProfile
      object={{
        ...table,
        properties: {
          table_profile: {
            columns: [
              null,
              { ...profile, null_rate: "unknown", inferred_type: "unknown" },
            ],
          },
        },
      }}
    />,
  );
  expect(screen.getAllByText("—")).toHaveLength(2);
});
