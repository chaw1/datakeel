import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { dataset } from "../test/fixtures";

import { LibraryPage } from "./LibraryPage";
it("renders the library and dataset cards", () => {
  render(
    <LibraryPage
      datasets={[dataset]}
      loading={false}
      setRefresh={vi.fn()}
      setSelectedId={vi.fn()}
      navigate={vi.fn()}
    />,
  );
  expect(
    screen.getByRole("heading", { name: "Sample collection" }),
  ).toBeVisible();
});
