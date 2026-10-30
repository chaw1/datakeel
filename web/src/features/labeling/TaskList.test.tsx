import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { labelingProject } from "../../test/labelingFixtures";

import { TaskList } from "./TaskList";
import { TaskSearch } from "./TaskSearch";

it("shows file names with their full path on hover instead of identities", () => {
  const open = vi.fn();
  render(
    <TaskList
      tasks={[...labelingProject.tasks]}
      samples={labelingProject.task_samples}
      risks={[]}
      onOpen={open}
    />,
  );
  const first = screen.getByRole("button", {
    name: "Open task harbor-001.png",
  });
  expect(first).toHaveTextContent("harbor-001.png");
  expect(first).toHaveAttribute("title", "harbor/day/harbor-001.png");
  expect(screen.queryByText(/task-1|sample-1/)).toBeNull();
  fireEvent.click(first);
  expect(open).toHaveBeenCalledWith(labelingProject.tasks[0]);
});

it("searches by file name after the typing pause", () => {
  vi.useFakeTimers();
  const search = vi.fn();
  render(<TaskSearch value="" onSearch={search} />);
  fireEvent.change(
    screen.getByRole("searchbox", { name: "Search file names" }),
    {
      target: { value: "harbor-00" },
    },
  );
  expect(search).not.toHaveBeenCalled();
  act(() => {
    vi.advanceTimersByTime(300);
  });
  expect(search).toHaveBeenCalledWith("harbor-00");
  vi.useRealTimers();
});
