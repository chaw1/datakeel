import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";

import { TrainingForm } from "./TrainingForm";

it.each([
  {
    locale: "en",
    label: "Annotation labels to balance",
    submit: "Preview distribution",
  },
  { locale: "zh", label: "分层使用的标注类型", submit: "预览分布" },
])(
  "submits each selected annotation source in $locale",
  async ({ locale, label, submit }) => {
    localStorage.setItem("datakeel.locale", locale);
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(
      <I18nProvider>
        <TrainingForm busy={false} onSubmit={onSubmit} />
      </I18nProvider>,
    );
    const select = screen.getByRole("combobox", { name: label });
    expect(select).toHaveAttribute("aria-label", label);
    expect(select).toHaveValue("all");
    expect(
      screen
        .getAllByRole("option")
        .filter((option) => option.parentElement === select),
    ).toHaveLength(4);
    for (const source of ["all", "classification", "detection", "spans"]) {
      await user.selectOptions(select, source);
      await user.click(screen.getByRole("button", { name: submit }));
      expect(onSubmit).toHaveBeenLastCalledWith(
        expect.objectContaining({ stratification_source: source }),
        true,
      );
    }
  },
);

it("disables source selection when generated stratification does not apply", async () => {
  const user = userEvent.setup();
  render(<TrainingForm busy={false} onSubmit={vi.fn()} />);
  const select = screen.getByRole("combobox", {
    name: "Annotation labels to balance",
  });
  await user.click(screen.getByLabelText("Balance all labels across sets"));
  expect(select).toBeDisabled();
  await user.click(screen.getByLabelText("Balance all labels across sets"));
  expect(select).toBeEnabled();
  await user.selectOptions(screen.getByLabelText("Split source"), "directory");
  expect(select).toBeDisabled();
});
