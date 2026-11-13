import type { HTMLAttributes, ReactNode } from "react";

export type SurfaceVariant = "sheet" | "paper" | "ledger";

export interface SurfaceProps extends HTMLAttributes<HTMLElement> {
  as?: "div" | "section" | "article";
  variant?: SurfaceVariant;
  children: ReactNode;
}

export function Surface({
  as = "div",
  variant = "sheet",
  className = "",
  children,
  ...props
}: SurfaceProps) {
  const classes = [
    "card",
    "ui-surface",
    variant !== "sheet" ? `ui-surface-${variant}` : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  if (as === "section")
    return (
      <section className={classes} {...props}>
        {children}
      </section>
    );
  if (as === "article")
    return (
      <article className={classes} {...props}>
        {children}
      </article>
    );
  return (
    <div className={classes} {...props}>
      {children}
    </div>
  );
}
