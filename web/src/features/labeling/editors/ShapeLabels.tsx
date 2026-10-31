import { ShapeLabel } from "./ShapeLabel";

import type { ChipAnchor } from "./chipLayout";
import type { LabelStyle } from "./labelColors";

/**
 * Every shape's chip, in shape order. Editors draw these after all shapes and drafts, so no
 * shape covers another shape's name and, where chips overlap, the later shape's chip is on top.
 */
export function ShapeLabels({
  chips,
}: {
  chips: readonly (ChipAnchor & { style: LabelStyle })[];
}) {
  return (
    <>
      {chips.map((chip, index) => (
        <ShapeLabel
          key={index}
          x={chip.x}
          y={chip.y}
          bounds={chip.bounds}
          style={chip.style}
        />
      ))}
    </>
  );
}
