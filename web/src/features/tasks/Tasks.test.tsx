import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { task } from "../../test/fixtures";

import { Tasks } from "./Tasks";
it("renders task state and progress", () => {
  render(<Tasks tasks={[task]} />);
  expect(screen.getByText("Completed")).toBeVisible();
  expect(screen.getByText("100%")).toBeVisible();
});

it("marks a partial task and lists its failed recordings", () => {
  render(
    <Tasks
      tasks={[
        {
          ...task,
          partial: true,
          failed_files: [
            {
              file_id: "file-2",
              filename: "broken.mp4",
              operator: "video.probe",
              reason: "ExecutionError: moov atom not found",
            },
          ],
        },
      ]}
    />,
  );
  expect(
    screen.getByText("Partially completed: some recordings failed"),
  ).toBeVisible();
  const failures = screen.getByRole("list", { name: "Failed recordings" });
  expect(failures).toHaveTextContent(
    "broken.mp4 · video.probe: ExecutionError: moov atom not found",
  );
});
