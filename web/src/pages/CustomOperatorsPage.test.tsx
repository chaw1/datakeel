import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n/I18nProvider";
import { actionRun } from "../test/actionFixtures";
import {
  customActionRun,
  customCode,
  customHash,
  customPlan,
  customRun,
  customVersion,
} from "../test/customOperatorFixtures";
import { dataset } from "../test/fixtures";

import { CustomOperatorsPage } from "./CustomOperatorsPage";

import type { ActionPlan } from "../api/types";

function mockApi(unsafe = false, currentPlan = () => customPlan) {
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    let value: unknown = [];
    if (path.endsWith("/configuration"))
      value = {
        backend: unsafe ? "subprocess" : "container",
        subprocess_enabled: unsafe,
        container_image: "python@sha256:fixture",
      };
    else if (init?.method === "POST")
      value = path.endsWith("/runs")
        ? customActionRun
        : path.endsWith("/execute")
          ? { ...actionRun, action_type: "submit_custom_operator" }
          : currentPlan();
    else if (path.endsWith("/submissions")) value = [currentPlan()];
    else if (path.endsWith("/runs")) value = [customRun];
    else value = [customVersion];
    return Promise.resolve(new Response(JSON.stringify(value)));
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}
function renderPage() {
  return render(
    <CustomOperatorsPage
      datasets={[dataset]}
      onDataChanged={vi.fn()}
      onOpenReceipt={vi.fn()}
    />,
  );
}

async function prepareInlinePlan() {
  const user = userEvent.setup();
  await user.type(
    screen.getByRole("textbox", { name: "Operator name" }),
    "fixture_filter",
  );
  await user.click(
    screen.getByRole("textbox", { name: "Complete Python source" }),
  );
  await user.paste(customCode);
  await user.click(
    screen.getByRole("button", { name: "Submit for code review" }),
  );
  await screen.findByRole("button", {
    name: "Approve and register custom operator code",
  });
  return user;
}

it("submits exact source and shows the frozen full-code approval before any execution", async () => {
  const fetch = mockApi();
  const { container } = renderPage();
  await screen.findByText("fixture_filter", { selector: "h3" });
  const user = userEvent.setup();
  await user.type(
    screen.getByRole("textbox", { name: "Operator name" }),
    "fixture_filter",
  );
  await user.click(
    screen.getByRole("textbox", { name: "Complete Python source" }),
  );
  await user.paste(customCode);
  await user.click(
    screen.getByRole("button", { name: "Submit for code review" }),
  );
  expect(
    await screen.findByRole("button", {
      name: "Approve and register custom operator code",
    }),
  ).toBeVisible();
  expect(
    container.querySelector(".approval-sheet .custom-source code")?.textContent,
  ).toBe(customCode);
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0]?.[1]?.body).toBe(
    JSON.stringify({
      name: "fixture_filter",
      code: customCode,
      modality: "text",
    }),
  );
  expect(
    screen.getByRole("link", { name: "Open approval sheet" }),
  ).toHaveAttribute("href", `#/approvals?plan=${customPlan.id}`);
});

it("rejects non-object parameters locally then queues the pinned approved version", async () => {
  const fetch = mockApi();
  renderPage();
  const user = userEvent.setup();
  const parameters = await screen.findByRole("textbox", {
    name: "Parameters (JSON object) · fixture_filter",
  });
  await user.clear(parameters);
  await user.click(parameters);
  await user.paste("[]");
  await user.click(screen.getByRole("button", { name: "Run in pipeline" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Parameters must be a valid JSON object.",
  );
  expect(
    fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
  ).toHaveLength(0);
  await user.clear(parameters);
  await user.click(parameters);
  await user.paste('{"contains":"keep"}');
  await user.click(screen.getByRole("button", { name: "Run in pipeline" }));
  expect(await screen.findByText(/Pipeline queued/)).toBeVisible();
  const posted = fetch.mock.calls.find(([, init]) => init?.method === "POST");
  expect(posted?.[0]).toBe(`/api/custom-operators/${customHash}/runs`);
  expect(posted?.[1]?.body).toBe(
    JSON.stringify({
      dataset_id: dataset.id,
      name: "fixture_filter",
      params: { contains: "keep" },
    }),
  );
  expect(screen.getByText("timeout")).toBeVisible();
  expect(
    screen.getByText(customRun.image_digest, { exact: true }),
  ).toBeVisible();
});

it("always warns when unsafe subprocess execution is enabled and translates the complete form", async () => {
  localStorage.setItem("datakeel.locale", "zh");
  mockApi(true);
  render(
    <I18nProvider>
      <CustomOperatorsPage
        datasets={[dataset]}
        onDataChanged={vi.fn()}
        onOpenReceipt={vi.fn()}
      />
    </I18nProvider>,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "已启用不安全的开发执行后端",
  );
  expect(screen.getByRole("alert")).toHaveTextContent("禁止用于外部提交代码");
  expect(
    screen.getByRole("textbox", { name: "完整 Python 源码" }),
  ).toBeVisible();
  expect(screen.getByRole("button", { name: "在算子链中运行" })).toBeDisabled();
  expect(screen.getByRole("region", { name: "沙箱运行记录" })).toBeVisible();
});

it("reports a version read failure without claiming empty versions and retries", async () => {
  const fetch = mockApi();
  fetch.mockImplementationOnce(() =>
    Promise.resolve(
      new Response(JSON.stringify({ detail: "Version store unavailable" }), {
        status: 503,
      }),
    ),
  );
  renderPage();
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "503 Version store unavailable",
  );
  expect(
    screen.queryByText("No code has been approved yet."),
  ).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  expect(screen.getByText("fixture_filter", { selector: "h3" })).toBeVisible();
});

it.each(["REJECTED", "EXECUTED", "FAILED"] as const)(
  "refresh removes the inline pending sheet after an external %s decision",
  async (status) => {
    let current: ActionPlan = customPlan;
    const fetch = mockApi(false, () => current);
    const { container } = renderPage();
    const user = await prepareInlinePlan();
    current = { ...customPlan, status };
    await user.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => {
      expect(container.querySelector(".approval-sheet")).toBeNull();
    });
    expect(container.querySelector(".custom-submissions")).toHaveTextContent(
      status === "REJECTED"
        ? "Rejected"
        : status === "EXECUTED"
          ? "Executed"
          : "Failed",
    );
    expect(
      fetch.mock.calls.filter(([, init]) => init?.method === "POST"),
    ).toHaveLength(1);
  },
);

it("refresh adopts an existing approval and executes without requesting a second signature", async () => {
  let current: ActionPlan = customPlan;
  const fetch = mockApi(false, () => current);
  const { container } = renderPage();
  const user = await prepareInlinePlan();
  current = { ...customPlan, status: "APPROVED" };
  await user.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() => {
    expect(container.querySelector(".approval-kicker")).toHaveTextContent(
      "Approved",
    );
  });
  await user.click(
    screen.getByRole("button", {
      name: "Approve and register custom operator code",
    }),
  );
  await waitFor(() => {
    expect(container.querySelector(".approval-sheet")).toBeNull();
  });
  expect(
    fetch.mock.calls
      .filter(([, init]) => init?.method === "POST")
      .map(([path]) => path),
  ).toEqual(["/api/custom-operators", `/api/actions/${customPlan.id}/execute`]);
});

it("removes a rejected inline sheet and refreshes its durable rejected status", async () => {
  let current: ActionPlan = customPlan;
  const fetch = mockApi(false, () => current);
  const { container } = renderPage();
  const user = await prepareInlinePlan();
  current = { ...customPlan, status: "REJECTED" };
  await user.click(screen.getByRole("button", { name: "Return" }));
  await waitFor(() => {
    expect(container.querySelector(".approval-sheet")).toBeNull();
    expect(container.querySelector(".custom-submissions")).toHaveTextContent(
      "Rejected",
    );
  });
  const decision = fetch.mock.calls.find(
    ([path]) => path === `/api/approvals/${customPlan.id}`,
  );
  expect(decision?.[1]?.body).toContain('"approve":false');
  expect(fetch.mock.calls.some(([path]) => path.endsWith("/execute"))).toBe(
    false,
  );
});

it("reopens an approved submission after page reload and reuses its digest and operation without resigning", async () => {
  const approved: ActionPlan = { ...customPlan, status: "APPROVED" };
  const fetch = mockApi(false, () => approved);
  const { container } = renderPage();
  const user = userEvent.setup();
  await user.click(
    await screen.findByRole("button", { name: "Open approval sheet" }),
  );
  expect(container.querySelector(".approval-kicker")).toHaveTextContent(
    "Approved",
  );
  await user.click(
    screen.getByRole("button", {
      name: "Approve and register custom operator code",
    }),
  );
  await waitFor(() => {
    expect(container.querySelector(".approval-sheet")).toBeNull();
  });
  const posts = fetch.mock.calls.filter(([, init]) => init?.method === "POST");
  expect(posts).toHaveLength(1);
  expect(posts[0]?.[0]).toBe(`/api/actions/${approved.id}/execute`);
  expect(posts[0]?.[1]?.body).toBe(
    JSON.stringify({
      plan_digest: approved.plan_digest,
      actor: "local",
      operation_id: approved.operation_id,
    }),
  );
});
