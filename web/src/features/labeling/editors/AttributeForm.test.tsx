import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { attributeFieldsFixture } from "../../../test/attributeFixtures";

import { AttributeForm } from "./AttributeForm";

import type { Attributes } from "./types";

function mount(advanced = false, initial: Attributes = {}) {
  const changed = vi.fn<(value: Attributes) => void>();
  function Harness() {
    const [value, setValue] = useState<Attributes>(initial);
    return (
      <AttributeForm
        label="Box 1"
        fields={attributeFieldsFixture}
        value={value}
        advanced={advanced}
        onChange={(next) => {
          changed(next);
          setValue(next);
        }}
      />
    );
  }
  render(<Harness />);
  return changed;
}

it("fills all five attribute types with native controls and the keyboard", async () => {
  const user = userEvent.setup();
  const changed = mount();
  expect(screen.queryByText("Advanced: raw attributes")).toBeNull();
  expect(screen.queryByRole("textbox", { name: /json/i })).toBeNull();
  await user.tab();
  expect(screen.getByRole("checkbox", { name: "Occluded" })).toHaveFocus();
  await user.keyboard(" ");
  await user.tab();
  const colour = screen.getByRole("combobox", { name: "Colour (required)" });
  expect(colour).toHaveFocus();
  await user.selectOptions(colour, "blue");
  await user.tab();
  await user.keyboard(" ");
  await user.tab();
  await user.keyboard(" ");
  await user.tab();
  expect(screen.getByRole("spinbutton", { name: "Count" })).toHaveFocus();
  await user.keyboard("7");
  await user.tab();
  await user.keyboard("left lane");
  expect(changed.mock.lastCall?.[0]).toEqual({
    occluded: true,
    color: "blue",
    tags: ["dirty", "wet"],
    count: 7,
    note: "left lane",
  });
  await user.selectOptions(colour, "");
  expect(changed.mock.lastCall?.[0]).not.toHaveProperty("color");
});

it("flags values the template does not allow and keeps raw JSON for managers", () => {
  mount(true, { color: "green", count: 99 });
  expect(
    screen.getByRole("combobox", { name: "Colour (required)" }),
  ).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByRole("spinbutton", { name: "Count" })).toHaveAttribute(
    "aria-invalid",
    "true",
  );
  expect(screen.getByText("Advanced: raw attributes")).toBeInTheDocument();
});
