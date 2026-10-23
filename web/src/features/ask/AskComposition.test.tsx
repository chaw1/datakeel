import { createEvent, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { AskHistory } from "./AskHistory";
import { AskResolution } from "./AskResolution";
import { retailAnswer, unavailableAnswer } from "./testFixtures";

const actions = ["candidate", "replay", "todo"] as const;
type Action = (typeof actions)[number];

function renderAction(action: Action) {
  const activated = vi.fn();
  if (action === "candidate")
    render(
      <AskResolution
        answer={{ ...unavailableAnswer, status: "clarification" }}
        onChooseMetric={activated}
      />,
    );
  else if (action === "replay")
    render(
      <AskHistory
        answers={[retailAnswer]}
        currentId={retailAnswer.id}
        onReplay={activated}
      />,
    );
  else render(<AskResolution answer={unavailableAnswer} />);
  const button = screen.getAllByRole("button")[0];
  return {
    button,
    assertIdle() {
      expect(activated).not.toHaveBeenCalled();
      expect(
        screen.queryByRole("textbox", { name: "Metric request draft" }),
      ).not.toBeInTheDocument();
    },
    assertActivated() {
      if (action === "todo")
        expect(
          screen.getByRole("textbox", { name: "Metric request draft" }),
        ).toBeVisible();
      else
        expect(activated).toHaveBeenCalledExactlyOnceWith(
          action === "candidate" ? "retail_revenue" : retailAnswer.id,
        );
    },
  };
}

it.each(actions)(
  "blocks %s Enter activation and direct clicks between compositionstart and compositionend",
  async (action) => {
    const user = userEvent.setup();
    const control = renderAction(action);
    control.button.focus();
    fireEvent.compositionStart(control.button);
    await user.keyboard("{Enter}");
    await user.click(control.button);
    control.assertIdle();
    fireEvent.compositionEnd(control.button);
    await user.keyboard("{Enter}");
    control.assertActivated();
  },
);

it.each(actions)(
  "prevents the native Enter default click for %s when only isComposing is true",
  async (action) => {
    const user = userEvent.setup();
    const control = renderAction(action);
    control.button.focus();
    const enter = createEvent.keyDown(control.button, {
      key: "Enter",
      code: "Enter",
      isComposing: true,
      cancelable: true,
    });
    fireEvent(control.button, enter);
    expect(enter.defaultPrevented).toBe(true);
    control.assertIdle();
    await user.keyboard("{Enter}");
    control.assertActivated();
  },
);
