import { Icon } from "../Icon";

import type { IconName } from "../Icon";
import type { InputHTMLAttributes } from "react";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  icon?: IconName;
  mono?: boolean;
  wrapperClassName?: string;
}

export function Input({
  icon,
  mono = false,
  wrapperClassName = "",
  className = "",
  ...props
}: InputProps) {
  const inputClass = [mono ? "ui-mono" : "", className]
    .filter(Boolean)
    .join(" ");
  if (icon) {
    const fieldClass = ["ui-input-field", wrapperClassName]
      .filter(Boolean)
      .join(" ");
    return (
      <span className={fieldClass}>
        <Icon name={icon} size={15} />
        <input className={inputClass} {...props} />
      </span>
    );
  }
  return (
    <input
      className={["ui-input", inputClass].filter(Boolean).join(" ")}
      {...props}
    />
  );
}
