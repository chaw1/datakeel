import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it } from "vitest";

import { QuestionEvidence } from "./QuestionEvidence";

it("uses NFC code point offsets and retains overlapping match sources", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <QuestionEvidence
      question={"😀Cafe\u0301零售额?"}
      matches={[
        {
          start: 5,
          end: 8,
          text: "零售额",
          source: "metric:retail",
          match_kind: "exact",
        },
        {
          start: 6,
          end: 8,
          text: "售额",
          source: "term:revenue",
          match_kind: "synonym",
        },
      ]}
    />,
  );
  expect(
    container.querySelector(".ask-highlighted-question"),
  ).toHaveTextContent("😀Café零售额?");
  expect(
    [...container.querySelectorAll("mark")]
      .map((node) => node.textContent)
      .join(""),
  ).toBe("零售额");
  expect(screen.getByTitle("metric:retail · term:revenue")).toHaveTextContent(
    "售额",
  );
  await user.click(screen.getByText("Match sources"));
  expect(screen.getByText("term:revenue")).toBeVisible();
});

it("shows the unmodified question when no terms match", () => {
  const { container } = render(
    <QuestionEvidence question="Unknown question" matches={[]} />,
  );
  expect(screen.getByText("Unknown question")).toBeVisible();
  expect(
    screen.getByText("No registered terms matched the question."),
  ).toBeVisible();
  expect(container.querySelector("mark")).toBeNull();
});
