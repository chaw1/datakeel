import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { quality } from "../../test/fixtures";

import Quality from "./Quality";
it("renders scores and explains excluded annotation evidence", () => {
  render(<Quality quality={quality} />);
  expect(screen.getByText("83.5")).toBeVisible();
  expect(
    screen.getByText(
      "No annotation evidence. Remaining weights are normalized.",
    ),
  ).toBeVisible();
});
