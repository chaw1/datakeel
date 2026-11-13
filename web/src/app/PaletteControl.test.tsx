import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";

import { PaletteControl } from "./PaletteControl";

beforeEach(() => {
  localStorage.removeItem("datakeel.palette");
  document.documentElement.removeAttribute("data-palette");
});

it("defaults to pencil without data-palette and switches between ochre and graphite", async () => {
  const user = userEvent.setup();
  render(<PaletteControl />);
  const control = screen.getByRole("combobox", { name: "Palette" });
  expect(control).toHaveValue("pencil");
  expect(document.documentElement).not.toHaveAttribute("data-palette");

  await user.selectOptions(control, "ochre");
  expect(document.documentElement.dataset.palette).toBe("ochre");
  expect(localStorage.getItem("datakeel.palette")).toBe("ochre");

  await user.selectOptions(control, "graphite");
  expect(document.documentElement.dataset.palette).toBe("graphite");
  expect(localStorage.getItem("datakeel.palette")).toBe("graphite");

  await user.selectOptions(control, "pencil");
  expect(document.documentElement).not.toHaveAttribute("data-palette");
});

it("restores the saved palette on mount", () => {
  localStorage.setItem("datakeel.palette", "graphite");
  render(<PaletteControl />);
  expect(screen.getByRole("combobox", { name: "Palette" })).toHaveValue(
    "graphite",
  );
  expect(document.documentElement.dataset.palette).toBe("graphite");
});
