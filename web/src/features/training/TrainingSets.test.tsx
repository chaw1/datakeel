import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { I18nProvider } from "../../i18n/I18nProvider";
import { version } from "../../test/fixtures";

import { leakage, splitSet } from "./testFixtures";
import { TrainingSets } from "./TrainingSets";

it("previews configured ratios without saving and saves a named immutable split", async () => {
  const user = userEvent.setup();
  let saved = false;
  const fetch = vi.fn((path: string, init?: RequestInit) => {
    if (init?.method === "POST" && path.endsWith("/splits")) saved = true;
    return Promise.resolve(
      new Response(
        JSON.stringify(
          init?.method === "POST" ? splitSet : saved ? [splitSet] : [],
        ),
      ),
    );
  });
  vi.stubGlobal("fetch", fetch);
  render(<TrainingSets datasetId="dataset-1" versions={[version]} />);
  await screen.findByText("No split sets have been saved for this version.");
  await user.clear(screen.getByLabelText("Split set name"));
  await user.type(screen.getByLabelText("Split set name"), "baseline");
  await user.type(screen.getByLabelText("Group metadata field"), "batch");
  await user.click(
    screen.getByRole("button", { name: "Preview distribution" }),
  );
  await screen.findByText("Preview only. Save the split to enable export.");
  expect(
    screen.queryByRole("button", { name: "Review export plan" }),
  ).not.toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/versions/version-1/training/preview",
    expect.objectContaining({ body: JSON.stringify(splitSet.request) }),
  );
  await user.click(
    screen.getByRole("button", { name: "Save immutable split" }),
  );
  await screen.findByRole("button", { name: "Review export plan" });
  expect(screen.getByLabelText("Saved split set")).toHaveValue(splitSet.id);
  expect(fetch).toHaveBeenCalledWith(
    "/api/datasets/dataset-1/versions/version-1/training/splits",
    expect.objectContaining({ method: "POST" }),
  );
});

it("compares saved class distribution and exposes zero counts in the chart", async () => {
  const user = userEvent.setup();
  const comparison = {
    ...splitSet,
    id: "split-2",
    request: { ...splitSet.request, name: "seed-7", seed: 7 },
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify([splitSet, comparison]))),
    ),
  );
  render(<TrainingSets datasetId="dataset-1" versions={[version]} />);
  await screen.findByRole("heading", { name: "baseline" });
  await user.selectOptions(
    screen.getByLabelText("Compare with another split"),
    "split-2",
  );
  expect(
    screen.getByRole("heading", { name: "Distribution comparison" }),
  ).toBeVisible();
  const distribution = screen.getByRole("region", {
    name: "Class distribution: seed-7",
  });
  expect(
    within(distribution).getByRole("meter", {
      name: "bridge, train: 0 of 1 samples",
    }),
  ).toHaveAttribute("value", "0");
  expect(
    within(distribution).getByRole("meter", {
      name: "harbor, test: 1 of 1 samples",
    }),
  ).toHaveAttribute("value", "1");
  await user.click(screen.getByText("Inspect sample membership"));
  expect(screen.getByText("sample-c")).toBeVisible();
});

it("reads directory splits and renders all four kinds of pair evidence", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string, init?: RequestInit) =>
    Promise.resolve(
      new Response(
        JSON.stringify(
          path.endsWith("/leakage")
            ? leakage
            : init?.method === "POST"
              ? splitSet
              : [splitSet],
        ),
      ),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(<TrainingSets datasetId="dataset-1" versions={[version]} />);
  await screen.findByRole("heading", { name: "baseline" });
  await user.selectOptions(screen.getByLabelText("Split source"), "directory");
  expect(screen.getByLabelText("Random seed")).toBeDisabled();
  await user.click(
    screen.getByRole("button", { name: "Save immutable split" }),
  );
  await waitFor(() => {
    expect(
      fetch.mock.calls.some(
        ([, init]) =>
          typeof init?.body === "string" &&
          init.body.includes('"source":"directory"'),
      ),
    ).toBe(true);
  });
  await user.click(screen.getByRole("button", { name: "Check leakage" }));
  await screen.findByRole("table", { name: "4 cross-set evidence pairs" });
  for (const name of [
    "Identical content",
    "Similar images",
    "Similar text",
    "Shared group",
  ])
    expect(screen.getByRole("rowheader", { name })).toBeVisible();
  expect(screen.getByText("image evidence")).toBeVisible();
  expect(
    within(
      screen.getByRole("table", { name: "4 cross-set evidence pairs" }),
    ).getAllByText("sample-a"),
  ).toHaveLength(4);
});

it("clears selected-version data and reports read failures with retry", async () => {
  const user = userEvent.setup();
  const fetch = vi.fn((path: string) =>
    Promise.resolve(
      path.includes("version-2")
        ? new Response(JSON.stringify({ detail: "Version unavailable" }), {
            status: 404,
          })
        : new Response(JSON.stringify([splitSet])),
    ),
  );
  vi.stubGlobal("fetch", fetch);
  render(
    <TrainingSets
      datasetId="dataset-1"
      versions={[version, { ...version, id: "version-2" }]}
    />,
  );
  await screen.findByRole("heading", { name: "baseline" });
  await user.selectOptions(
    screen.getByLabelText("Training source version"),
    "version-2",
  );
  await screen.findByText(/404 Version unavailable/);
  expect(
    screen.queryByRole("heading", { name: "baseline" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(
      fetch.mock.calls.filter(([path]) => path.includes("version-2")),
    ).toHaveLength(2);
  });
});

it("renders the Chinese empty state without requesting data for an absent version", () => {
  const fetch = vi.fn();
  vi.stubGlobal("fetch", fetch);
  localStorage.setItem("datakeel.locale", "zh");
  render(
    <I18nProvider>
      <TrainingSets datasetId="dataset-1" versions={[]} />
    </I18nProvider>,
  );
  expect(screen.getByRole("heading", { name: "训练集" })).toBeVisible();
  expect(screen.getByText("导入数据集版本后即可生成训练集。")).toBeVisible();
  expect(fetch).not.toHaveBeenCalled();
});
