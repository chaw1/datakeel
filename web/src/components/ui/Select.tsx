import type { SelectHTMLAttributes } from "react";

export type SelectSize = "sm" | "md";

export interface SelectProps extends Omit<
  SelectHTMLAttributes<HTMLSelectElement>,
  "size"
> {
  size?: SelectSize;
}

export function Select({
  size = "md",
  className = "",
  children,
  ...props
}: SelectProps) {
  const classes = ["ui-select", size === "sm" ? "ui-select-sm" : "", className]
    .filter(Boolean)
    .join(" ");
  return (
    <select className={classes} {...props}>
      {children}
    </select>
  );
}
