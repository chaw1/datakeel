import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { dataset, workspace } from "../test/fixtures";

import { DatasheetsPage } from "./DatasheetsPage";

it("renders the dataset datasheet tab and its version selection", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(() => Promise.resolve(new Response("[]"))),
  );
  render(<DatasheetsPage data={workspace} selectedId={dataset.id} />);
  expect(screen.getByRole("heading", { name: "Datasheet" })).toBeVisible();
  expect(await screen.findByLabelText("Dataset version")).toHaveValue(
    "version-1",
  );
});
