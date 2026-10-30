import { createContext } from "react";

/** The drawer element that receives the selected annotation's details, or null to render inline. */
export const DetailsSlotContext = createContext<HTMLElement | null>(null);

/** Current canvas scale, so overlays can keep a constant on-screen size at any zoom. */
export const CanvasScaleContext = createContext(1);
