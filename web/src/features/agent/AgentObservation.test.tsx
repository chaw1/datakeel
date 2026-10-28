import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { I18nContext, translator } from "../../i18n/context";
import { agentEvent } from "../../test/agentFixtures";

import { AgentObservation } from "./AgentObservation";

const props = {
  dryRun: false,
  busy: false,
  onResolved: vi.fn(),
  onOpenReceipt: vi.fn(),
};
it("shows a known stop reason once in the selected language", () => {
  render(
    <AgentObservation
      {...props}
      event={agentEvent("stopped", {
        stop_reason: "approval_required",
        text: "Stopped: approval_required.",
      })}
    />,
  );
  expect(screen.getByText("Waiting for your approval")).toBeVisible();
  expect(
    screen.queryByText("Stopped: approval_required."),
  ).not.toBeInTheDocument();
});
it("preserves details for an unfamiliar stop reason", () => {
  render(
    <AgentObservation
      {...props}
      event={agentEvent("stopped", {
        stop_reason: "provider_error",
        text: "Unexpected provider response",
      })}
    />,
  );
  expect(screen.getByText("provider_error")).toBeVisible();
  expect(screen.getByText("Unexpected provider response")).toBeVisible();
});

it("explains a canary stop without rendering its attached protected content", () => {
  render(
    <AgentObservation
      event={agentEvent("stopped", {
        stop_reason: "canary_leak",
        text: "PROTECTED_SESSION_VALUE",
      })}
      dryRun={false}
      busy={false}
      onResolved={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  expect(screen.getByRole("status")).toHaveTextContent(
    "protected session marker",
  );
  expect(screen.queryByText("PROTECTED_SESSION_VALUE")).not.toBeInTheDocument();
});

it.each(["en", "zh"] as const)(
  "explains workflow confirmation in %s without exposing the machine stop reason",
  (locale) => {
    render(
      <I18nContext.Provider
        value={{ locale, setLocale: vi.fn(), t: translator(locale) }}
      >
        <AgentObservation
          {...props}
          event={agentEvent("stopped", {
            stop_reason: "workflow_confirmation_required",
            text: "Stopped: workflow_confirmation_required.",
          })}
        />
      </I18nContext.Provider>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      locale === "en"
        ? "Confirm the workflow before applying changes."
        : "请确认工作流后再执行更改。",
    );
    expect(screen.getByRole("status")).not.toHaveTextContent(
      "workflow_confirmation_required",
    );
  },
);
