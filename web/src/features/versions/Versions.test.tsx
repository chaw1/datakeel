import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { version } from "../../test/fixtures";

import { Versions } from "./Versions";
it("opens the stored manifest for inspection", async () => {
  const user = userEvent.setup();
  render(<Versions versions={[version]} />);
  await user.click(screen.getByText("Inspect manifest snapshot"));
  expect(screen.getByText(/processed.txt/)).toBeVisible();
});
