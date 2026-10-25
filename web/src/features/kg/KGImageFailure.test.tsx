import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { assert, expect, it } from "vitest";

import { imageExplanation, imageRun } from "../../test/kgImageFixtures";

import { KGImageSource } from "./KGImageSource";
import { KGReports } from "./KGReports";

it("shows image failure text and removes boxes after a failed load, then recovers for another image", () => {
  const { rerender } = render(
    <KGImageSource
      source={imageExplanation.sources[0]}
      anchors={imageExplanation.relation.assertion.anchors}
    />,
  );
  fireEvent.error(screen.getByRole("img", { name: "diagram.png" }));
  expect(screen.getByText("Original image could not be loaded")).toBeVisible();
  expect(
    screen.queryByRole("img", { name: /Image evidence region/ }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Located on image")).not.toBeInTheDocument();
  rerender(
    <KGImageSource
      source={{ ...imageExplanation.sources[0], image_url: "/replacement.png" }}
      anchors={imageExplanation.relation.assertion.anchors}
    />,
  );
  expect(screen.getByRole("img", { name: "diagram.png" })).toHaveAttribute(
    "src",
    "/replacement.png",
  );
  expect(
    screen.getAllByRole("img", { name: /Image evidence region/ }),
  ).toHaveLength(2);
});

it("keeps known extraction cost visible when transcription pricing is unknown", async () => {
  assert(imageRun.report);
  render(
    <KGReports
      runs={[
        {
          ...imageRun,
          report: {
            ...imageRun.report,
            cost_usd: null,
            transcription_cost_usd: null,
            extraction_cost_usd: "0.0025",
          },
        },
      ]}
    />,
  );
  await userEvent
    .setup()
    .click(screen.getByText(/replay-demo/, { selector: "summary span" }));
  expect(
    screen.getByText("Transcription cost (USD)").nextElementSibling,
  ).toHaveTextContent("Unknown");
  expect(
    screen.getByText("Extraction cost (USD)").nextElementSibling,
  ).toHaveTextContent("0.002500");
});
