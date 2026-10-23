import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { ThemeControl } from "./ThemeControl";

it("persists an explicit theme and removes it when following the system", async () => {
  const user = userEvent.setup();
  render(<ThemeControl />);
  const control = screen.getByRole("combobox", { name: "Theme" });
  expect(control).toHaveValue("system");
  await user.selectOptions(control, "dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem("datakeel.theme")).toBe("dark");
  await user.selectOptions(control, "light");
  expect(document.documentElement.dataset.theme).toBe("light");
  await user.selectOptions(control, "system");
  expect(document.documentElement).not.toHaveAttribute("data-theme");
});

it("restores the saved choice on mount", () => {
  localStorage.setItem("datakeel.theme", "dark");
  render(<ThemeControl />);
  expect(screen.getByRole("combobox", { name: "Theme" })).toHaveValue("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  document.documentElement.removeAttribute("data-theme");
});
