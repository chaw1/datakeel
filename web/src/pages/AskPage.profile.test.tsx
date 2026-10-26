import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  ambiguousSensorAnswer,
  sensorAnswer,
} from "../features/ask/profileFixtures";

import { AskPage } from "./AskPage";

it("repeats the saved gap question with the chosen dataset and original reference", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(ambiguousSensorAnswer)))
    .mockResolvedValueOnce(new Response(JSON.stringify(sensorAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  const input = screen.getByRole("textbox", { name: "Business question" });
  await user.type(input, sensorAnswer.question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  const choice = await screen.findByRole("button", { name: "First sensors" });
  await user.clear(input);
  await user.type(input, "Edited question");
  await user.click(choice);
  expect(
    await screen.findByRole("table", {
      name: "Devices with recorded sampling gaps",
    }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question: sensorAnswer.question,
        reference_instant: sensorAnswer.reference_instant,
        session_id: sensorAnswer.session_id,
        subject_id: "sensors",
      }),
    }),
  );
});
