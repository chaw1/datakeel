import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { Anchor } from "./Anchor";

it("uses normalized code points and half-open intervals after astral and combining characters", () => {
  const active = vi.fn();
  const { container, rerender } = render(
    <Anchor
      text={"🚶 cafe\u0301 person!"}
      ranges={[{ start: 7, end: 13, id: "person", number: 2 }]}
      onActive={active}
    />,
  );
  expect(container.querySelector("mark")).toHaveTextContent(/^person$/);
  expect(container).toHaveTextContent("🚶 café person2!");
  const anchor = screen.getByRole("button", { name: "Anchor 2: person" });
  fireEvent.mouseEnter(anchor);
  expect(active).toHaveBeenLastCalledWith("person");
  rerender(
    <Anchor
      text={"🚶 cafe\u0301 person!"}
      ranges={[{ start: 7, end: 13, id: "person", number: 2 }]}
      activeId="person"
    />,
  );
  expect(anchor).toHaveClass("is-linked");
});
it("leaves text intact when supplied intervals are invalid instead of clamping to unrelated evidence", () => {
  const { container } = render(
    <Anchor
      text="abc"
      ranges={[
        { start: -1, end: 2, id: "negative", number: 1 },
        { start: 1, end: 9, id: "overflow", number: 2 },
        { start: 1, end: 1, id: "empty", number: 3 },
      ]}
    />,
  );
  expect(container).toHaveTextContent(/^abc$/);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
