import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { table } from "./fixtures";
import { MetadataEvidence } from "./MetadataEvidence";

it("renders source deletion, owners, schedule, state, freshness, and quality details", () => {
  render(
    <MetadataEvidence
      item={{
        ...table,
        properties: {
          integration: {
            system: "airflow",
            unique_id: "daily_orders",
            description: "Generated daily totals",
            owner: "Data team",
            tags: ["daily", "finance"],
            source_deleted: true,
            details: {
              schedule: { __type: "CronExpression", value: "@daily" },
              state: "success",
              last_success: "2026-10-25T10:00:00Z",
              quality: { passed: 3 },
            },
          },
        },
      }}
    />,
  );
  expect(screen.getByText("Deleted at source")).toBeVisible();
  expect(screen.getByText("Data team")).toBeVisible();
  expect(screen.getByText("daily, finance")).toBeVisible();
  expect(screen.getByText("success")).toBeVisible();
  expect(screen.getByText("2026-10-25T10:00:00Z")).toBeVisible();
  expect(screen.getByText(/@daily/, { selector: "dd" })).toBeVisible();
  expect(screen.getByText(/"passed": 3/)).toBeInTheDocument();
});

it("marks Airflow datasets filed under the placeholder as an unmatched source", () => {
  const airflow = (unmatched: boolean) => ({
    ...table,
    properties: {
      integration: {
        system: "airflow",
        unique_id: "postgres://ehr-db.example/ehr.public.orders",
        details: unmatched ? { placeholder: true, unmatched_source: true } : {},
      },
    },
  });
  const { rerender } = render(<MetadataEvidence item={airflow(true)} />);
  expect(screen.getByText("Unmatched source")).toHaveAttribute(
    "title",
    expect.stringContaining("airflow placeholder"),
  );
  rerender(<MetadataEvidence item={airflow(false)} />);
  expect(screen.queryByText("Unmatched source")).not.toBeInTheDocument();
});

it("adds no empty integration section to ordinary catalog tables", () => {
  const { container } = render(<MetadataEvidence item={table} />);
  expect(container).toBeEmptyDOMElement();
});

it("keeps dbt descriptions and shows the newest freshness across merged contributions", () => {
  render(
    <MetadataEvidence
      item={{
        ...table,
        properties: {
          source_deleted: false,
          integration: {
            system: "dbt",
            unique_id: "model.shop.orders",
            description: "Order model",
            source_deleted: true,
            details: {},
          },
          integrations: {
            "metadata:dbt:shop": {
              system: "dbt",
              unique_id: "model.shop.orders",
              source_deleted: true,
              details: {},
            },
            "metadata:airflow:scheduler": {
              system: "airflow",
              unique_id: "daily.orders",
              details: {
                last_success: "2026-10-25T10:00:00Z",
                state: "success",
              },
            },
            "openlineage:warehouse": {
              system: "openlineage",
              unique_id: "orders",
              details: {
                last_success: "2026-10-26T10:00:00Z",
                state: "COMPLETE",
              },
            },
          },
        },
      }}
    />,
  );
  expect(screen.getByText("Order model")).toBeVisible();
  expect(screen.getByText("2026-10-26T10:00:00Z")).toBeVisible();
  expect(screen.queryByText("Deleted at source")).not.toBeInTheDocument();
  expect(
    screen.getByText("The dbt source contribution was deleted."),
  ).toBeInTheDocument();
  expect(screen.getByText(/"COMPLETE"/)).toBeInTheDocument();
});
