import type { ReactNode } from "react";

export type BadgeTone =
  "neutral" | "accent" | "ok" | "warn" | "danger" | "stamp";

const legacyToneClass: Record<BadgeTone, string> = {
  neutral: "gray",
  accent: "gray",
  ok: "green",
  warn: "amber",
  danger: "red",
  stamp: "red",
};

export interface BadgeProps {
  tone?: BadgeTone;
  dot?: boolean;
  mono?: boolean;
  className?: string;
  children: ReactNode;
}

export function Badge({
  tone = "neutral",
  dot = false,
  mono = false,
  className = "",
  children,
}: BadgeProps) {
  const classes = [
    "badge",
    legacyToneClass[tone],
    "ui-badge",
    `ui-badge-${tone}`,
    mono ? "ui-mono" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <span className={classes}>
      {dot && <span className="status-dot" />}
      {children}
    </span>
  );
}
