import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { workspace } from "../test/fixtures";

import { OverviewPage } from "./OverviewPage";
it("renders overview quality and run progress", () => {
  render(
    <OverviewPage
      data={workspace}
      files={2}
      modalities={["text", "image"]}
      completed={1}
      running={false}
      navigate={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "A traceable journey" }),
  ).toBeVisible();
});
