import { Icon } from "../Icon";

import type { IconName } from "../Icon";
import type { ButtonHTMLAttributes } from "react";

export type ButtonVariant =
  "secondary" | "primary" | "danger" | "ghost" | "link";

export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: IconName;
  iconSize?: number;
}

export function Button({
  variant = "secondary",
  size = "md",
  icon,
  iconSize = 15,
  type = "button",
  className = "",
  children,
  ...props
}: ButtonProps) {
  const classes = [
    variant === "link" ? "text-button ui-button-link" : "button ui-button",
    variant !== "secondary" && variant !== "link" ? `ui-button-${variant}` : "",
    size !== "md" && variant !== "link" ? `ui-button-${size}` : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <button type={type} className={classes} {...props}>
      {icon && <Icon name={icon} size={iconSize} />}
      {children}
    </button>
  );
}
