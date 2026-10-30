import { expect, it } from "vitest";

import { contrast, labelStyle } from "./labelColors";

const tokens = {
  labels: ["#1f5fbf", "#b3261e", "#1e7b34"],
  ink: "#1b1d22",
  background: "#fffefa",
};
const labels = [
  { id: "cat", name: "Cat", attributes: {} },
  { id: "dog", name: "Dog", attributes: {} },
  { id: "car", name: "Car", color: "#FC0", attributes: {} },
  { id: "bus", name: "Bus", color: "tomato", attributes: {} },
];

it("takes the palette color by label order when the label set has no color", () => {
  expect(labelStyle(labels, "cat", tokens).stroke).toBe("#1f5fbf");
  expect(labelStyle(labels, "dog", tokens).stroke).toBe("#b3261e");
});

it("uses a configured hex color and picks the more legible chip text", () => {
  const style = labelStyle(labels, "car", tokens);
  expect(style.stroke).toBe("#ffcc00");
  expect(style.fill).toBe("#ffcc002e");
  expect(style.text).toBe(tokens.ink);
  expect(contrast(style.text, style.stroke)).toBeGreaterThan(
    contrast(tokens.background, style.stroke),
  );
});

it("falls back to the palette for unusable colors and wraps it for long label sets", () => {
  expect(labelStyle(labels, "bus", tokens)).toMatchObject({
    name: "Bus",
    stroke: "#1f5fbf",
  });
  expect(labelStyle(labels, "unknown", tokens).name).toBe("unknown");
});

it("measures WCAG contrast", () => {
  expect(contrast("#000", "#fff")).toBe(21);
  expect(contrast("#777777", "#777777")).toBe(1);
});
