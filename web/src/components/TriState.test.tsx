import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { TriState } from "./TriState";

it("gives all four states distinct text, shape classes, and accessible names", () => {
  render(
    <>
      <TriState value="present" />
      <TriState value="absent" />
      <TriState value="unknown" />
      <TriState value={null} />
    </>,
  );
  for (const [label, text, shape] of [
    ["Present", "Yes", "present"],
    ["Measured absent", "No", "absent"],
    ["Unknown", "?", "unknown"],
    ["No assertion recorded", "·", "missing"],
  ]) {
    const mark = screen.getByRole("img", { name: label });
    expect(mark).toHaveTextContent(text);
    expect(mark).toHaveClass(shape);
  }
});
