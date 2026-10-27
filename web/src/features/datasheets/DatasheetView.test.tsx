import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { DatasheetView } from "./DatasheetView";
import { sheet } from "./testFixtures";

it("renders all chapters and exposes the cited source on hover and click", async () => {
  const user = userEvent.setup();
  render(<DatasheetView sheet={sheet} />);
  expect(screen.getAllByRole("heading", { level: 3 })).toHaveLength(7);
  expect(
    screen.getAllByText("No record of this item exists in the platform."),
  ).toHaveLength(6);
  const sentence = screen.getByText("The dataset is Sample collection.");
  expect(sentence).toHaveAttribute(
    "title",
    expect.stringContaining("dataset dataset-1 · name"),
  );
  await user.click(sentence);
  expect(screen.getByText("fact-name", { selector: "dt code" })).toBeVisible();
  expect(
    screen.getByText('dataset dataset-1 · name: "Sample collection"', {
      selector: "dd",
    }),
  ).toBeVisible();
  expect(
    screen.getByRole("link", { name: "Download Markdown" }),
  ).toHaveAttribute("href", "/api/datasheets/sheet-1/download?format=markdown");
  expect(screen.getByRole("link", { name: "Download HTML" })).toHaveAttribute(
    "href",
    "/api/datasheets/sheet-1/download?format=html",
  );
  await user.click(screen.getByText("Removed sentences (1)"));
  expect(screen.getByText("Acme supplied 900 files.")).toBeVisible();
  expect(
    screen.getByText(
      "Number absent from cited facts · Proper name absent from cited facts",
    ),
  ).toBeVisible();
});

it("discloses missing facts in the selected document language", () => {
  render(<DatasheetView sheet={{ ...sheet, language: "zh" }} />);
  expect(screen.getAllByText("平台中没有这一项的记录。")).toHaveLength(6);
  expect(
    screen.queryByText("No record of this item exists in the platform."),
  ).not.toBeInTheDocument();
});

it("distinguishes an empty validated chapter from missing facts and explains structural rejection", async () => {
  const user = userEvent.setup();
  render(
    <DatasheetView
      sheet={{
        ...sheet,
        sections: sheet.sections.map((section) =>
          section.key === "composition"
            ? { ...section, sentences: [] }
            : section,
        ),
        dropped_sentences: [
          {
            text: "Rejected wording",
            fact_ids: ["fact-name"],
            reasons: ["wrong_chapter", "invalid_output"],
          },
        ],
      }}
    />,
  );
  expect(
    screen.getByText("No sentence passed citation validation."),
  ).toBeVisible();
  expect(
    screen.getAllByText("No record of this item exists in the platform."),
  ).toHaveLength(6);
  await user.click(screen.getByText("Removed sentences (1)"));
  expect(
    screen.getByText(
      "Cited facts belong to a different chapter · Model output does not match the required document structure",
    ),
  ).toBeVisible();
});
