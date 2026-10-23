import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

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
