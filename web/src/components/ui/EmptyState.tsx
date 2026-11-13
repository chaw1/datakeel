import { Icon } from "../Icon";

import type { IconName } from "../Icon";
import type { ReactNode } from "react";

export interface EmptyStateProps {
  icon?: IconName;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  card?: boolean;
  className?: string;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  card = false,
  className = "",
}: EmptyStateProps) {
  const classes = [card ? "card" : "", "empty-state", "ui-empty", className]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      {icon && <Icon name={icon} size={32} />}
      <h3>{title}</h3>
      {description && <p>{description}</p>}
      {action}
    </div>
  );
}
