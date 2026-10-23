import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { dataset } from "../../test/fixtures";
import { workflow } from "../../test/workflowFixtures";

import { WorkflowForm } from "./WorkflowForm";

it("uses schema defaults and prefilled dataset without automatically starting", async () => {
  const start = vi.fn();
  render(
    <WorkflowForm
      definition={workflow}
      datasets={[dataset]}
      datasetId={dataset.id}
      busy={false}
      onStart={start}
    />,
  );
  expect(screen.getByRole("combobox", { name: /Dataset/ })).toHaveValue(
    dataset.id,
  );
  expect(
    screen.getByRole("spinbutton", { name: /Maximum quality score/ }),
  ).toHaveValue(60);
  expect(start).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Run workflow" }));
  expect(start).toHaveBeenCalledWith({
    dataset_id: dataset.id,
    quality_max: 60,
  });
});
it("validates JSON objects and renders bilingual schema controls", async () => {
  const start = vi.fn();
  render(
    <I18nContext.Provider
      value={{ locale: "zh", setLocale: vi.fn(), t: translator("zh") }}
    >
      <WorkflowForm
        definition={{
          ...workflow,
          inputs: {
            override: {
              type: "object",
              required: true,
              default: { measure: { column: "amount" } },
              description: "",
            },
            enabled: {
              type: "boolean",
              default: false,
              required: true,
              description: "",
            },
            count: {
              type: "integer",
              default: 2,
              required: true,
              description: "",
            },
          },
        }}
        datasets={[]}
        datasetId=""
        busy={false}
        onStart={start}
      />
    </I18nContext.Provider>,
  );
  const input = screen.getByRole("textbox", { name: /定义覆盖项/ });
  await userEvent.clear(input);
  await userEvent.type(input, "[[]");
  await userEvent.click(screen.getByRole("button", { name: "运行工作流" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("object");
  expect(start).not.toHaveBeenCalled();
  await userEvent.clear(input);
  await userEvent.type(input, '{{"amount":42}');
  await userEvent.click(screen.getByRole("checkbox"));
  await userEvent.click(screen.getByRole("button", { name: "运行工作流" }));
  expect(start).toHaveBeenCalledWith({
    override: { amount: 42 },
    enabled: true,
    count: 2,
  });
});
