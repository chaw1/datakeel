import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import {
  knowledgeAnswer,
  shipmentSubject,
} from "../features/ask/knowledgeFixtures";
import { retailAnswer, unavailableAnswer } from "../features/ask/testFixtures";
import { I18nProvider } from "../i18n/I18nProvider";

import { AskPage } from "./AskPage";

it("keeps the original knowledge question when a clarification subject is selected", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          ...knowledgeAnswer,
          status: "clarification",
          subject_candidates: [shipmentSubject],
        }),
      ),
    )
    .mockResolvedValue(new Response(JSON.stringify(knowledgeAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.type(screen.getByRole("textbox"), knowledgeAnswer.question);
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(
    await screen.findByRole("button", {
      name: /出货额 Metric shipment_revenue/,
    }),
  );
  expect(
    await screen.findByRole("region", { name: "System records" }),
  ).toBeVisible();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question: knowledgeAnswer.question,
        reference_instant: knowledgeAnswer.reference_instant,
        session_id: knowledgeAnswer.session_id,
        subject_id: shipmentSubject.asset_ref.asset_id,
      }),
    }),
  );
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it("asks a sample question, follows catalog lineage, and replays the saved result", async () => {
  const fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(retailAnswer))),
  );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  const onOpenReceipt = vi.fn();
  render(<AskPage onOpenReceipt={onOpenReceipt} />);
  expect(screen.getByText("Start with a business question")).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", {
      name: "East China retail revenue · last quarter",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
    "4,979,475",
  );
  expect(fetch).toHaveBeenCalledWith(
    "/api/ask",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        actor: "local-user",
        question: retailAnswer.question,
        reference_instant: "2026-10-01T00:00:00Z",
      }),
    }),
  );
  await user.click(screen.getByRole("button", { name: "View lineage" }));
  expect(onOpenReceipt).toHaveBeenCalledWith({
    assetId: "retail_revenue",
    includeCatalog: true,
  });
  await user.click(screen.getByRole("button", { name: "Replay saved answer" }));
  expect(await screen.findByLabelText("Calculated result")).toHaveTextContent(
    "4,979,475",
  );
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask/answer-1",
    expect.objectContaining({ method: "GET" }),
  );
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("shows a pending request, rejects duplicate input, and replaces old numerical answers", async () => {
  let complete: ((response: Response) => void) | undefined;
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(retailAnswer)))
    .mockImplementationOnce(
      () =>
        new Promise<Response>((resolve) => {
          complete = resolve;
        }),
    );
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", {
      name: "East China retail revenue · last quarter",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await screen.findByLabelText("Calculated result");
  await user.click(
    screen.getByRole("button", { name: "Why did the return rate rise?" }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(screen.getByRole("status")).toHaveTextContent(
    "Finding records and evidence…",
  );
  expect(screen.getByRole("textbox")).toBeDisabled();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask",
    expect.objectContaining({
      body: JSON.stringify({
        actor: "local-user",
        question: unavailableAnswer.question,
        reference_instant: "2026-10-01T00:00:00Z",
        session_id: "session-1",
      }),
    }),
  );
  complete?.(new Response(JSON.stringify(unavailableAnswer)));
  expect(
    await screen.findByRole("heading", {
      name: "No registered metric can answer this question",
    }),
  ).toBeVisible();
  expect(screen.getByRole("textbox")).toBeEnabled();
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it("retries the failed operation without silently switching to edited form values", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({ detail: "Source temporarily unavailable" }),
        { status: 503 },
      ),
    )
    .mockResolvedValue(new Response(JSON.stringify(retailAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", {
      name: "East China retail revenue · last quarter",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "503 Source temporarily unavailable",
  );
  expect(
    screen.queryByText("Start with a business question"),
  ).not.toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "Why did the return rate rise?" }),
  );
  await user.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByLabelText("Calculated result")).toBeVisible();
  expect(fetch.mock.calls[0]).toEqual(fetch.mock.calls[1]);
});

it("retries failed replay through GET and preserves the saved metric version", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response(JSON.stringify(retailAnswer)))
    .mockResolvedValueOnce(
      new Response(JSON.stringify({ detail: "Read unavailable" }), {
        status: 500,
      }),
    )
    .mockResolvedValue(new Response(JSON.stringify(retailAnswer)));
  vi.stubGlobal("fetch", fetch);
  const user = userEvent.setup();
  render(<AskPage onOpenReceipt={vi.fn()} />);
  await user.click(
    screen.getByRole("button", {
      name: "East China retail revenue · last quarter",
    }),
  );
  await user.click(screen.getByRole("button", { name: "Ask data" }));
  await user.click(
    await screen.findByRole("button", { name: "Replay saved answer" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "500 Read unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await user.click(
    await screen.findByRole("link", { name: "a · Metric definition" }),
  );
  expect(screen.getByText("Version 2")).toBeVisible();
  expect(fetch.mock.calls[1]).toEqual(fetch.mock.calls[2]);
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/ask/answer-1",
    expect.objectContaining({ method: "GET" }),
  );
});

it("renders the question controls and reference date explanation in Chinese", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  render(
    <I18nProvider>
      <AskPage onOpenReceipt={vi.fn()} />
    </I18nProvider>,
  );
  expect(screen.getByRole("textbox", { name: "业务问题" })).toBeVisible();
  expect(screen.getByLabelText("计算基准日期（UTC）")).toHaveValue(
    "2026-10-01",
  );
  expect(screen.getByRole("button", { name: "开始问数" })).toBeDisabled();
  await waitFor(() => {
    expect(document.documentElement.lang).toBe("zh");
  });
});
