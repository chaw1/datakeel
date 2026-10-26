import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { readObjectTarget } from "../object/navigation";

import { AskAnswerView } from "./AskAnswerView";
import { ProfileAnswerView } from "./ProfileAnswerView";
import { ambiguousSensorAnswer, sensorAnswer } from "./profileFixtures";

it("renders measured sampling-axis rankings with original row and version links", async () => {
  const user = userEvent.setup();
  render(<AskAnswerView answer={sensorAnswer} onOpenReceipt={vi.fn()} />);
  expect(screen.getByText("Answered from published profiles")).toBeVisible();
  const table = screen.getByRole("table", {
    name: "Devices with recorded sampling gaps",
  });
  const device = within(table).getByRole("row", { name: "beta 1 3" });
  expect(device).toBeVisible();
  expect(
    screen.getByText(/do not establish missing values specific/),
  ).toBeVisible();
  expect(
    screen.queryByText("No rows matched this question."),
  ).not.toBeInTheDocument();
  await user.click(screen.getByText("beta", { selector: "summary" }));
  const file = screen.getByRole("link", { name: "sensors.csv" });
  expect(readObjectTarget(file.getAttribute("href") ?? "")).toMatchObject({
    kind: "file",
    id: "original",
    datasetId: "sensors",
    versionId: "import",
    tab: "facts",
  });
  expect(screen.getByText(/Original CSV rows: 7, 3/)).toBeVisible();
  const source = screen.getByRole("link", { name: "Original source version" });
  expect(readObjectTarget(source.getAttribute("href") ?? "")).toMatchObject({
    kind: "version",
    id: "import",
    datasetId: "sensors",
  });
  expect(screen.queryByLabelText("Calculated result")).not.toBeInTheDocument();
});

it("exposes dataset choices without a numeric result in ambiguous or refused states", async () => {
  const choose = vi.fn();
  const user = userEvent.setup();
  const { rerender } = render(
    <ProfileAnswerView
      answer={ambiguousSensorAnswer}
      onChooseDataset={choose}
    />,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "First sensors" }));
  expect(choose).toHaveBeenCalledWith("sensors");
  rerender(
    <ProfileAnswerView answer={{ ...sensorAnswer, status: "unanswerable" }} />,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Total missing duration (seconds)"),
  ).not.toBeInTheDocument();
});

it("ignores an absent optional profile payload", () => {
  const { container } = render(
    <ProfileAnswerView answer={{ ...sensorAnswer, profile: null }} />,
  );
  expect(container).toBeEmptyDOMElement();
});
