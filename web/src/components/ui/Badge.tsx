import type { HTMLAttributes, ReactNode } from "react";

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

export interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  tone?: BadgeTone;
  dot?: boolean;
  mono?: boolean;
  children: ReactNode;
}

export function Badge({
  tone = "neutral",
  dot = false,
  mono = false,
  className = "",
  children,
  ...props
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
    <span className={classes} {...props}>
      {dot && <span className="status-dot" />}
      {children}
    </span>
  );
}
