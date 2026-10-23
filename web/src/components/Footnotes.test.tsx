import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { FootnoteReference } from "./FootnoteReference";
import { Footnotes, footnoteMarker, uniqueFootnotes } from "./Footnotes";

it("deduplicates by source identity while preserving first occurrence order and label", async () => {
  const user = userEvent.setup();
  const onExpand = vi.fn();
  const items = [
    { id: "extractor-v2", label: "Extractor v2", href: "#/object/version/v2" },
    { id: "event-1", label: "Raw event", onExpand },
    { id: "extractor-v2", label: "Duplicate", href: "#/wrong" },
  ];
  render(<Footnotes items={items} />);
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "Extractor v2" })).toHaveAttribute(
    "href",
    "#/object/version/v2",
  );
  expect(screen.queryByText("Duplicate")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Raw event" }));
  expect(onExpand).toHaveBeenCalledOnce();
  expect(uniqueFootnotes(items).map((item) => item.id)).toEqual([
    "extractor-v2",
    "event-1",
  ]);
  expect([0, 25, 26, 51, 52].map(footnoteMarker)).toEqual([
    "a",
    "z",
    "aa",
    "az",
    "ba",
  ]);
});

it("opens the referenced source without replacing the application hash route", async () => {
  const user = userEvent.setup();
  const definition = "Registered definition v2";
  const item = {
    id: "answer:metric",
    label: "Metric",
    content: <p>{definition}</p>,
  };
  const hash = window.location.hash;
  render(
    <>
      <FootnoteReference item={item} index={0} />
      <Footnotes items={[item]} />
    </>,
  );
  expect(screen.getByText("Registered definition v2")).not.toBeVisible();
  await user.click(screen.getByRole("link", { name: "a · Metric" }));
  expect(screen.getByText("Registered definition v2")).toBeVisible();
  expect(window.location.hash).toBe(hash);
  expect(screen.getByText("Metric")).toHaveFocus();
});
