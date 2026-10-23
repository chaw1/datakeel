import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { task } from "../../test/fixtures";

import { Tasks } from "./Tasks";
it("renders task state and progress", () => {
  render(<Tasks tasks={[task]} />);
  expect(screen.getByText("Completed")).toBeVisible();
  expect(screen.getByText("100%")).toBeVisible();
});
