import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { workspace } from "../test/fixtures";

import { TasksPage } from "./TasksPage";
it("renders task history", () => {
  render(<TasksPage data={workspace} />);
  expect(screen.getByRole("heading", { name: "Run history" })).toBeVisible();
});
