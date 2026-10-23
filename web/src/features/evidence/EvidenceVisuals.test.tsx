import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { mention, sample } from "../../test/evidenceFixtures";

import { AssertionChip } from "./AssertionChip";
import { CaptionEvidence } from "./CaptionEvidence";
import { SamplePreview } from "./SamplePreview";

it("highlights NFC Unicode code points after an astral character", () => {
  const { container } = render(
    <CaptionEvidence caption={sample.caption} spans={sample.caption_spans} />,
  );
  expect(container.querySelector("mark")).toHaveTextContent(/^person$/);
  expect(container).toHaveTextContent("🚶 café person1 and car.");
});
it("scales xyxy annotation boxes using original-image dimensions", () => {
  render(<SamplePreview sample={sample} />);
  expect(screen.getByRole("img", { name: "Annotation: person" })).toHaveStyle({
    left: "10%",
    top: "10%",
    width: "50%",
    height: "50%",
  });
  expect(screen.getByRole("img", { name: sample.filename })).toHaveAttribute(
    "src",
    sample.thumbnail_url,
  );
});
it("renders corrupt image placeholders without a broken img request", () => {
  const { container } = render(
    <SamplePreview sample={{ ...sample, thumbnail_url: null }} />,
  );
  expect(screen.getByRole("img", { name: "Image unavailable" })).toBeVisible();
  expect(container.querySelector("img")).toBeNull();
});
it("distinguishes unknown evidence and displays its extractor version", () => {
  render(
    <AssertionChip
      assertion={{
        ...mention,
        object: { concept: "person", value: "unknown" },
      }}
    />,
  );
  expect(screen.getByText("Unknown")).toBeVisible();
  expect(screen.getByText("evidence.caption_mentions · 1.0")).toBeVisible();
});
