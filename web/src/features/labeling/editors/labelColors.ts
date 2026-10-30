import type { ProductionLabel } from "./types";

/** Number of `--label-N` theme tokens; each passes the contrast gate in light and dark. */
export const LABEL_PALETTE_SIZE = 8;

const HEX = /^#(?:[\da-f]{3}|[\da-f]{6})$/i;

export interface LabelStyle {
  name: string;
  stroke: string;
  fill: string;
  text: string;
}

function expand(hex: string) {
  const digits = hex.slice(1);
  return `#${
    digits.length === 3
      ? digits.replace(/[\da-f]/gi, (digit) => digit + digit)
      : digits
  }`.toLowerCase();
}

function luminance(hex: string) {
  const channels = (expand(hex).slice(1).match(/../g) ?? []).map((value) => {
    const channel = parseInt(value, 16) / 255;
    return channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  const [red = 0, green = 0, blue = 0] = channels;
  return red * 0.2126 + green * 0.7152 + blue * 0.0722;
}

/** WCAG 2 contrast ratio between two opaque hex colors. */
export function contrast(a: string, b: string) {
  const first = luminance(a);
  const second = luminance(b);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

/**
 * Use the label set's configured color, otherwise the theme palette by label order.
 * Chip text takes whichever theme text color contrasts more with the label color.
 */
export function labelStyle(
  labels: readonly ProductionLabel[],
  category: string,
  tokens: { labels: readonly string[]; ink: string; background: string },
): LabelStyle {
  const index = labels.findIndex((item) => item.id === category);
  const label = index >= 0 ? labels[index] : undefined;
  const configured = label?.color?.trim() ?? "";
  const palette = tokens.labels.filter(Boolean);
  const fallback =
    palette.length > 0
      ? (palette[(index >= 0 ? index : 0) % palette.length] ?? "")
      : "";
  const stroke = HEX.test(configured) ? expand(configured) : fallback;
  const candidates = [tokens.background, tokens.ink].filter((value) =>
    HEX.test(value),
  );
  const text = HEX.test(stroke)
    ? candidates.reduce(
        (best, value) =>
          contrast(value, stroke) > contrast(best, stroke) ? value : best,
        candidates[0] ?? tokens.background,
      )
    : tokens.background;
  return {
    name: label?.name ?? category,
    stroke,
    // Hex with an alpha suffix keeps the fill translucent without a literal color.
    fill: HEX.test(stroke) ? `${stroke}2e` : "",
    text,
  };
}
