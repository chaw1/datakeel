import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { graph } from "../../test/fixtures";

import { archiveProjection } from "./archiveModel";
import { GraphCanvas } from "./GraphCanvas";

it("shows a visible scroll cue only when columns overflow and can reach either end", async () => {
  const { container } = render(
    <GraphCanvas
      projection={archiveProjection(graph)}
      selected={null}
      onSelect={vi.fn()}
    />,
  );
  const scroller = container.querySelector<HTMLDivElement>(".graph-scroll");
  if (!scroller) throw new Error("Missing graph scroller");
  expect(container.querySelector(".graph-scroll-hint")).toBeNull();
  const scrollTo = vi.fn();
  Object.defineProperties(scroller, {
    clientWidth: { value: 900, configurable: true },
    scrollWidth: { value: 1500, configurable: true },
    scrollTo: { value: scrollTo, configurable: true },
  });
  fireEvent(window, new Event("resize"));
  expect(
    screen.getByText("Scroll horizontally to see all relations"),
  ).toBeVisible();
  expect(
    screen.getByRole("button", { name: "Show relations to the left" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Show relations to the right" }),
  );
  expect(scrollTo).toHaveBeenCalledWith({
    left: 1500,
    behavior: "smooth",
  });
  scroller.scrollLeft = 600;
  fireEvent.scroll(scroller);
  expect(
    screen.getByRole("button", { name: "Show relations to the right" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Show relations to the left" }),
  );
  expect(scrollTo).toHaveBeenCalledWith({
    left: 0,
    behavior: "smooth",
  });
  scroller.scrollLeft = 0;
  Object.defineProperty(scroller, "clientWidth", { value: 1600 });
  fireEvent(window, new Event("resize"));
  expect(container.querySelector(".graph-scroll-hint")).toBeNull();
});
