import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { PolygonEditor } from "./PolygonEditor";

import type { ReactNode } from "react";

// Konva stand-ins that expose whether a group receives pointer events.
vi.mock("react-konva", async () => {
  const { createElement } = await import("react");
  const node = ({ children }: { children?: ReactNode }) =>
    createElement("div", null, children);
  return {
    Stage: node,
    Layer: node,
    Image: node,
    Rect: node,
    Transformer: node,
    Circle: node,
    Line: node,
    Label: node,
    Tag: node,
    Text: node,
    Group: ({
      children,
      listening,
    }: {
      children?: ReactNode;
      listening?: boolean;
    }) =>
      createElement(
        "div",
        { "data-testid": "group", "data-listening": String(listening ?? true) },
        children,
      ),
  };
});

it("stops existing polygons from catching clicks while a new polygon is being drawn", () => {
  render(
    <PolygonEditor
      labels={[{ id: "cat", name: "Cat", shortcut: "1", attributes: {} }]}
      template={{
        id: "template",
        name: "Template",
        annotation_type: "polygon",
        revision: 1,
        archived: false,
        attributes: [],
        component_config: {},
      }}
      value={{
        sample_id: "sample",
        annotator_id: "local",
        image_width: 2000,
        image_height: 1500,
        polygons: [
          {
            category: "cat",
            points: [
              { x: 0, y: 0 },
              { x: 2000, y: 0 },
              { x: 2000, y: 1500 },
            ],
            attributes: {},
          },
        ],
      }}
      onChange={vi.fn()}
    />,
  );
  const shapes = () =>
    screen
      .getAllByTestId("group")
      .filter((group) => group.querySelector("[data-testid=group]") === null);
  // Not drawing: clicking an existing polygon still selects it.
  expect(shapes().every((group) => group.dataset.listening === "true")).toBe(
    true,
  );
  fireEvent.keyDown(screen.getByRole("region", { name: "Polygons" }), {
    key: "p",
  });
  // Drawing: the press reaches the stage and adds a point, even inside the old polygon.
  expect(shapes().some((group) => group.dataset.listening === "false")).toBe(
    true,
  );
});
