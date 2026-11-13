export interface TabItem<T extends string> {
  id: T;
  label: string;
  count?: number;
}

export interface SegmentedTabsProps<T extends string> {
  label: string;
  items: readonly TabItem<T>[];
  activeId: T;
  onSelect: (id: T) => void;
  className?: string;
}

export function SegmentedTabs<T extends string>({
  label,
  items,
  activeId,
  onSelect,
  className = "",
}: SegmentedTabsProps<T>) {
  return (
    <nav
      className={["tabs", "ui-tabs", className].filter(Boolean).join(" ")}
      aria-label={label}
    >
      {items.map((item) => (
        <button
          key={item.id}
          type="button"
          aria-current={activeId === item.id ? "page" : undefined}
          className={activeId === item.id ? "active" : ""}
          onClick={() => {
            onSelect(item.id);
          }}
        >
          {item.label}
          {item.count !== undefined && <span>{item.count}</span>}
        </button>
      ))}
    </nav>
  );
}
