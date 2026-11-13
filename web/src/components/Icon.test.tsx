import { render } from "@testing-library/react";
import { expect, it } from "vitest";

import { Icon } from "./Icon";

import type { IconName } from "./Icon";

const iconNames: readonly IconName[] = [
  "database",
  "activity",
  "lineage",
  "quality",
  "report",
  "arrow",
  "file",
  "grid",
  "check",
  "download",
  "search",
  "clock",
  "refresh",
  "chevron",
  "image",
  "close",
  "layers",
  "message",
  "workbench",
  "annotation",
  "catalog",
  "asset",
  "standards",
  "ask",
  "evidence",
  "kg",
  "rules",
  "operator",
  "workflow",
  "agent",
  "memory",
  "trace",
  "ontology",
  "palette",
];

it("renders every semantic icon as an accessible single-stroke SVG", () => {
  for (const name of iconNames) {
    const { container, unmount } = render(<Icon name={name} />);
    const svg = container.querySelector("svg");
    expect(svg, name).not.toBeNull();
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg?.children.length, name).toBeGreaterThan(0);
    unmount();
  }
});
