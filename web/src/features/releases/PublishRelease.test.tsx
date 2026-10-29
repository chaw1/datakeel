import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { actionPlan } from "../../test/actionFixtures";
import { dataset, version } from "../../test/fixtures";

import { PublishRelease } from "./PublishRelease";

const plan = { ...actionPlan, action_type: "publish_release" };

function renderForm() {
  render(
    <PublishRelease
      versions={[version, { ...version, id: "version-2" }]}
      datasetId={dataset.id}
      onChanged={vi.fn()}
    />,
  );
  return userEvent.setup();
}

it.each([
  "Semantic version tag",
  "Release notes",
  "Source version",
  "Maximum files",
  "Maximum size (GiB)",
])("clears the frozen release plan when %s changes", async (field) => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response(JSON.stringify(plan)))),
  );
  const user = renderForm();
  await user.click(screen.getByText("Publish a release"));
  await user.type(screen.getByLabelText("Semantic version tag"), "v1.2.0");
  await user.click(screen.getByRole("button", { name: "Review release plan" }));
  expect(await screen.findByRole("article")).toBeVisible();
  if (field === "Source version") {
    await user.selectOptions(screen.getByLabelText(field), "version-2");
  } else {
    await user.type(
      screen.getByLabelText(field),
      field.startsWith("Maximum") ? "2" : "x",
    );
  }
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Review release plan" }));
  expect(await screen.findByRole("article")).toBeVisible();
});

it("does not restore an outdated plan when a field changes during preparation", async () => {
  let complete!: (response: Response) => void;
  const response = new Promise<Response>((resolve) => {
    complete = resolve;
  });
  vi.stubGlobal(
    "fetch",
    vi.fn(() => response),
  );
  const user = renderForm();
  await user.click(screen.getByText("Publish a release"));
  await user.type(screen.getByLabelText("Semantic version tag"), "v1.2.0");
  const review = screen.getByRole("button", { name: "Review release plan" });
  await user.click(review);
  await user.type(screen.getByLabelText("Semantic version tag"), "-changed");
  complete(new Response(JSON.stringify(plan)));
  await waitFor(() => {
    expect(review).toBeEnabled();
  });
  expect(screen.queryByRole("article")).not.toBeInTheDocument();
});
