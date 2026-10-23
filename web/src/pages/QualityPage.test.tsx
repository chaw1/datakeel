import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { dataset, workspace } from "../test/fixtures";

import { QualityPage } from "./QualityPage";

it("requests server-calculated quality for each quarantine state", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(workspace.quality))),
  );
  vi.stubGlobal("fetch", fetch);
  render(<QualityPage data={workspace} selectedId={dataset.id} />);
  expect(fetch).not.toHaveBeenCalled();
  const filter = screen.getByRole("combobox", { name: "Quarantine status" });
  await user.selectOptions(filter, "true");
  expect(await screen.findByText("One small file")).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/datasets/dataset-1/quality?quarantined=true",
    expect.anything(),
  );
  await user.selectOptions(filter, "false");
  expect(await screen.findByText("One small file")).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/datasets/dataset-1/quality?quarantined=false",
    expect.anything(),
  );
  await user.selectOptions(filter, "all");
  expect(screen.getByText("One small file")).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("shows a filtered quality error without presenting unfiltered scores", async () => {
  const user = userEvent.setup();
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.reject(new Error("Unavailable"))),
  );
  render(<QualityPage data={workspace} selectedId={dataset.id} />);
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Quarantine status" }),
    "true",
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Unavailable");
  expect(screen.queryByText("One small file")).not.toBeInTheDocument();
  await user.selectOptions(
    screen.getByRole("combobox", { name: "Quarantine status" }),
    "all",
  );
  expect(screen.getByText("One small file")).toBeVisible();
});

it("renders quality evidence", () => {
  render(<QualityPage data={workspace} selectedId={dataset.id} />);
  expect(screen.getByText("One small file")).toBeVisible();
});
