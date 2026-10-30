import { render } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { BoxShape } from "./BoxShape";
import { PolygonShape } from "./PolygonShape";

import type Konva from "konva";

const shapes = vi.hoisted<{
  rectangle: Record<string, unknown>;
  circles: Record<string, unknown>[];
  node: Konva.Rect | null;
}>(() => ({
  rectangle: {},
  circles: [],
  node: null,
}));
vi.mock("react-konva", async () => {
  const { createElement, forwardRef, useImperativeHandle } =
    await import("react");
  const Rect = forwardRef<unknown, Record<string, unknown>>((props, ref) => {
    shapes.rectangle = props;
    useImperativeHandle(ref, () => shapes.node);
    return createElement("div");
  });
  return {
    Rect,
    Transformer: () => createElement("div"),
    Line: () => createElement("div"),
    Circle: (props: Record<string, unknown>) => {
      shapes.circles.push(props);
      return createElement("div");
    },
    Label: () => createElement("div"),
    Tag: () => createElement("div"),
    Text: () => createElement("div"),
  };
});
const shapeStyle = {
  name: "Cat",
  stroke: "var(--pencil)",
  fill: "",
  text: "var(--sheet)",
};
beforeEach(() => {
  shapes.rectangle = {};
  shapes.circles = [];
  shapes.node = null;
});
function fakeNode(x: number, y: number) {
  return {
    x: () => x,
    y: () => y,
    width: () => 400,
    height: () => 300,
    scaleX: () => 1,
    scaleY: () => 1,
    position: vi.fn(),
    size: vi.fn(),
    scale: vi.fn(),
  };
}
function drag(
  props: Record<string, unknown>,
  node: ReturnType<typeof fakeNode>,
) {
  const handler = props.onDragEnd;
  if (typeof handler !== "function") throw new Error("Missing drag commit");
  (handler as (event: { target: ReturnType<typeof fakeNode> }) => void)({
    target: node,
  });
}
it("snaps an imperatively dragged box back even when its clamped record is unchanged", () => {
  const value = {
    category: "cat",
    x1: 1600,
    y1: 100,
    x2: 2000,
    y2: 400,
    attributes: {},
  };
  const changed = vi.fn();
  render(
    <BoxShape
      value={value}
      selected={false}
      style={shapeStyle}
      width={2000}
      height={1500}
      onSelect={vi.fn()}
      onChange={changed}
    />,
  );
  const node = fakeNode(1900, 100);
  drag(shapes.rectangle, node);
  expect(changed).toHaveBeenCalledWith(value);
  expect(node.position).toHaveBeenCalledWith({ x: 1600, y: 100 });
});
it("sets all clamped transform geometry before resetting scale", () => {
  const node = fakeNode(-20, -10);
  shapes.node = node as unknown as Konva.Rect;
  const changed = vi.fn();
  render(
    <BoxShape
      value={{ category: "cat", x1: 0, y1: 0, x2: 400, y2: 300 }}
      selected={false}
      style={shapeStyle}
      width={2000}
      height={1500}
      onSelect={vi.fn()}
      onChange={changed}
    />,
  );
  const handler = shapes.rectangle.onTransformEnd;
  if (typeof handler !== "function")
    throw new Error("Missing transform commit");
  (handler as () => void)();
  expect(node.position).toHaveBeenCalledWith({ x: 0, y: 0 });
  expect(node.size).toHaveBeenCalledWith({ width: 380, height: 290 });
  expect(node.scale).toHaveBeenCalledWith({ x: 1, y: 1 });
  expect(changed).toHaveBeenCalledWith({
    category: "cat",
    x1: 0,
    y1: 0,
    x2: 380,
    y2: 290,
  });
});
it("snaps a vertex at the source boundary before emitting an unchanged polygon", () => {
  const value = {
    category: "cat",
    points: [
      { x: 2000, y: 100 },
      { x: 1500, y: 100 },
      { x: 1500, y: 500 },
    ],
    attributes: {},
  };
  const changed = vi.fn();
  render(
    <PolygonShape
      value={value}
      selected
      selectedPoint={0}
      style={shapeStyle}
      width={2000}
      height={1500}
      onSelect={vi.fn()}
      onPoint={vi.fn()}
      onChange={changed}
    />,
  );
  const vertex = shapes.circles.at(0);
  if (!vertex) throw new Error("Missing selected vertex");
  const node = fakeNode(2100, 100);
  drag(vertex, node);
  expect(node.position).toHaveBeenCalledWith({ x: 2000, y: 100 });
  expect(changed).toHaveBeenCalledWith(value);
});
