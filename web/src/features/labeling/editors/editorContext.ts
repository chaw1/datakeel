import { createContext } from "react";

import type { Bounds } from "./chipLayout";

/** The drawer element that receives the selected annotation's details, or null to render inline. */
export const DetailsSlotContext = createContext<HTMLElement | null>(null);

/** Current canvas scale, so overlays can keep a constant on-screen size at any zoom. */
export const CanvasScaleContext = createContext(1);

/** The image area currently on screen, in image pixels; null before the canvas is measured. */
export const CanvasViewContext = createContext<Bounds | null>(null);
