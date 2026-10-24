import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { kgPlan, kgProfile, kgSchema } from "../../test/kgFixtures";

import { KGApprovalEstimate } from "./KGApprovalEstimate";
import { KGExtractionForm } from "./KGExtractionForm";

it("shows destination and token limits with unknown cost rather than zero", () => {
  render(<KGApprovalEstimate plan={kgPlan} />);
  expect(
    screen.getByText("Destination host").nextElementSibling,
  ).toHaveTextContent("model.example.com");
  expect(screen.getByText("Documents").nextElementSibling).toHaveTextContent(
    "24",
  );
  expect(
    screen.getByText("Estimated input tokens").nextElementSibling,
  ).toHaveTextContent("12000");
  expect(
    screen.getByText("Maximum output tokens per call").nextElementSibling,
  ).toHaveTextContent("2048");
  expect(
    screen.getByText("Estimated cost upper bound").nextElementSibling,
  ).toHaveTextContent("Unknown");
});
it("prepares the selected profile and freezes controls without executing an external plan", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(kgPlan))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(
    <KGExtractionForm
      datasetId="dataset-1"
      versionId="version-1"
      schemas={[kgSchema]}
      profiles={[
        kgProfile,
        {
          ...kgProfile,
          id: "cloud",
          extractor: "llm",
          provider: "openai",
          model: "review-model",
        },
      ]}
      onChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
  await user.click(
    screen.getByText("Prepare graph extraction", { selector: "summary" }),
  );
  await user.selectOptions(
    screen.getByLabelText("Extraction profile"),
    "cloud",
  );
  await user.type(screen.getByLabelText("Token budget (optional)"), "50000");
  await user.type(
    screen.getByLabelText("Cost budget in USD (optional)"),
    "2.5",
  );
  await user.click(
    screen.getByRole("button", { name: "Prepare graph extraction" }),
  );
  const plan = await screen.findByRole("article", {
    name: "Action plan: run_kg_extraction",
  });
  expect(within(plan).getByText("Unknown")).toBeVisible();
  expect(
    within(plan).getByRole("button", {
      name: /Approve and extract a knowledge graph/,
    }),
  ).toBeEnabled();
  expect(screen.getByLabelText("Extraction profile")).toBeDisabled();
  expect(fetch).toHaveBeenCalledOnce();
  expect(fetch).toHaveBeenCalledWith(
    "/api/actions/run_kg_extraction/prepare",
    expect.objectContaining({
      body: JSON.stringify({
        dataset_id: "dataset-1",
        version_id: "version-1",
        schema_id: "business",
        profile_id: "cloud",
        budget_tokens: 50000,
        max_cost_usd: "2.5",
      }),
    }),
  );
});
