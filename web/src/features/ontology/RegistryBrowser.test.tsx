import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ontology } from "../../test/actionFixtures";

import { RegistryBrowser } from "./RegistryBrowser";
it("browses object, link, function and action definitions with their schemas", async () => {
  const user = userEvent.setup();
  render(<RegistryBrowser registry={ontology} />);
  expect(screen.getByRole("heading", { name: "dataset" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Link types 1" }));
  expect(screen.getByRole("heading", { name: "derived" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Functions 1" }));
  expect(screen.getByRole("heading", { name: "list_datasets" })).toBeVisible();
  await user.click(screen.getByRole("button", { name: "Actions 1" }));
  expect(screen.getByRole("heading", { name: "delete_files" })).toBeVisible();
  await user.click(screen.getByText("Schema", { exact: true }));
  expect(screen.getByText(/"params_schema"/)).toBeVisible();
});

it("shows the registered inverse of a reversible action", async () => {
  const user = userEvent.setup();
  render(
    <RegistryBrowser
      registry={{
        ...ontology,
        actions: ontology.actions.map((action) => ({
          ...action,
          id: "quarantine_files",
          reversible: true,
          inverse_of: "unquarantine_files",
        })),
      }}
    />,
  );
  await user.click(screen.getByRole("button", { name: "Actions 1" }));
  expect(screen.getByText("Inverse action")).toBeVisible();
  expect(screen.getByText("unquarantine_files")).toBeVisible();
});
