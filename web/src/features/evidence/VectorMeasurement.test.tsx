import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { evidenceRef } from "../../test/evidenceFixtures";
import { vectorGap } from "../../test/vectorFixtures";

import { VectorMeasurement } from "./VectorMeasurement";

it("renders cosine boundaries, the complete R and anchors", () => {
  render(<VectorMeasurement assertion={vectorGap} />);
  expect(screen.getByText("0.2")).toBeVisible();
  expect(screen.getByText("0.8")).toBeVisible();
  expect(screen.getByText("Complete frozen R / digest")).toBeVisible();
});
it("renders a stable cluster and every member", () => {
  render(
    <VectorMeasurement
      assertion={{
        ...vectorGap,
        object: {
          ...evidenceRef,
          asset_type: "semantic_cluster",
          asset_id: "stable-cluster",
        },
        measurement: {
          type: "cluster_config",
          eps: 0.2,
          min_samples: 2,
          config_hash: "a".repeat(64),
          role: "border",
          members: [evidenceRef],
        },
      }}
    />,
  );
  expect(screen.getByText("stable-cluster")).toBeVisible();
  expect(screen.getByText(/border/)).toBeVisible();
});
it("labels DBSCAN noise without implying corruption", () => {
  render(
    <VectorMeasurement
      assertion={{
        ...vectorGap,
        measurement: {
          type: "outlier_config",
          eps: 0.2,
          min_samples: 2,
          config_hash: "a".repeat(64),
        },
      }}
    />,
  );
  expect(
    screen.getByText("DBSCAN noise; does not imply corruption"),
  ).toBeVisible();
});
