import type { ReactNode } from "react";

export interface PageHeaderProps {
  title: ReactNode;
  subtitle?: ReactNode;
  eyebrow?: ReactNode;
  backAction?: ReactNode;
  actions?: ReactNode;
  compact?: boolean;
  className?: string;
  titleClassName?: string;
}

export function PageHeader({
  title,
  subtitle,
  eyebrow,
  backAction,
  actions,
  compact = false,
  className = "",
  titleClassName,
}: PageHeaderProps) {
  const classes = [
    "page-heading",
    "ui-page-header",
    compact ? "ui-page-header-compact" : "",
    className,
  ]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={classes}>
      <div>
        {backAction}
        {eyebrow && <span className="eyebrow">{eyebrow}</span>}
        <h1 className={titleClassName}>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {actions && <div className="ui-page-header-actions">{actions}</div>}
    </div>
  );
}
