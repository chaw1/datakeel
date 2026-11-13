export type IconName =
  | "database"
  | "activity"
  | "lineage"
  | "quality"
  | "report"
  | "arrow"
  | "file"
  | "grid"
  | "check"
  | "download"
  | "search"
  | "clock"
  | "refresh"
  | "chevron"
  | "image"
  | "close"
  | "layers"
  | "message"
  | "workbench"
  | "annotation"
  | "catalog"
  | "asset"
  | "standards"
  | "ask"
  | "evidence"
  | "kg"
  | "rules"
  | "operator"
  | "workflow"
  | "agent"
  | "memory"
  | "trace"
  | "ontology"
  | "palette"
  | "sidebar"
  | "user";
const paths: Record<IconName, React.ReactNode> = {
  message: (
    <path d="M20 15a3 3 0 0 1-3 3H8l-5 4V6a3 3 0 0 1 3-3h11a3 3 0 0 1 3 3v9ZM7 8h9M7 12h6" />
  ),
  database: (
    <>
      <ellipse cx="12" cy="5" rx="8" ry="3" />
      <path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </>
  ),
  activity: <path d="M3 12h4l3-8 4 16 3-8h4" />,
  lineage: (
    <>
      <rect x="2" y="9" width="6" height="6" rx="1.5" />
      <rect x="16" y="2" width="6" height="6" rx="1.5" />
      <rect x="16" y="16" width="6" height="6" rx="1.5" />
      <path d="M8 12h4V5h4M12 12v7h4" />
    </>
  ),
  quality: (
    <>
      <path d="m12 2 8 4v6c0 5-8 10-8 10S4 17 4 12V6l8-4Z" />
      <path d="m8 12 3 3 5-6" />
    </>
  ),
  report: (
    <>
      <path d="M14 2H5v20h14V7l-5-5Z" />
      <path d="M14 2v6h5M8 12h8M8 16h8" />
    </>
  ),
  arrow: <path d="M4 12h16m-6-6 6 6-6 6" />,
  file: (
    <>
      <path d="M14 2H5v20h14V7l-5-5Z" />
      <path d="M14 2v6h5" />
    </>
  ),
  grid: (
    <>
      <rect x="3" y="3" width="7" height="7" rx="1" />
      <rect x="14" y="3" width="7" height="7" rx="1" />
      <rect x="3" y="14" width="7" height="7" rx="1" />
      <rect x="14" y="14" width="7" height="7" rx="1" />
    </>
  ),
  check: <path d="m5 12 4 4L19 6" />,
  download: <path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5" />,
  search: (
    <>
      <circle cx="10" cy="10" r="6" />
      <path d="m15 15 6 6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 6v6l4 2" />
    </>
  ),
  refresh: (
    <path d="M20 8a8 8 0 0 0-14-3L3 8m0-5v5h5M4 16a8 8 0 0 0 14 3l3-3m0 5v-5h-5" />
  ),
  chevron: <path d="m9 5 7 7-7 7" />,
  image: (
    <>
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <circle cx="8" cy="8" r="1" />
      <path d="m3 17 6-6 5 5 3-3 4 4" />
    </>
  ),
  close: <path d="m6 6 12 12M6 18 18 6" />,
  layers: <path d="m12 3 10 5-10 5L2 8l10-5Zm-10 9 10 5 10-5M2 16l10 5 10-5" />,
  workbench: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M11 10v10" />
    </>
  ),
  annotation: (
    <>
      <path d="M4 8V5a1 1 0 0 1 1-1h3M16 4h3a1 1 0 0 1 1 1v3M20 16v3a1 1 0 0 1-1 1h-3M8 20H5a1 1 0 0 1-1-1v-3" />
      <path d="M9 12h6M12 9v6" />
    </>
  ),
  catalog: (
    <>
      <path d="M2 5h7a3 3 0 0 1 3 3v12a2 2 0 0 0-2-2H2V5Z" />
      <path d="M22 5h-7a3 3 0 0 0-3 3v12a2 2 0 0 1 2-2h8V5Z" />
    </>
  ),
  asset: (
    <path d="m12 3 8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12v9M12 12 4 7.5" />
  ),
  standards: (
    <>
      <rect x="4" y="3" width="16" height="18" rx="2" />
      <path d="m8 9 1.5 1.5L12 8M14 9h3M8 14h9M8 18h6" />
    </>
  ),
  ask: (
    <>
      <path d="M4 5h16a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H9l-5 4V7a2 2 0 0 1 2-2Z" />
      <path d="M8 13v-2M12 13V9M16 13v-4" />
    </>
  ),
  evidence: (
    <>
      <path d="M13 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-7" />
      <circle cx="15" cy="9" r="3.5" />
      <path d="m18 12 3 3M8 14h4M8 17h6" />
    </>
  ),
  kg: (
    <>
      <circle cx="6" cy="7" r="2.5" />
      <circle cx="18" cy="7" r="2.5" />
      <circle cx="12" cy="18" r="2.5" />
      <path d="M8.3 8.2 15.7 7M7.4 9.1l3.3 6.8M16.6 9.1l-3.3 6.8" />
    </>
  ),
  rules: (
    <>
      <path d="M4 7h16M4 12h16M4 17h16" />
      <circle cx="9" cy="7" r="2" />
      <circle cx="15" cy="12" r="2" />
      <circle cx="10" cy="17" r="2" />
    </>
  ),
  operator: <path d="m8 8-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14" />,
  workflow: (
    <>
      <circle cx="5" cy="12" r="2.5" />
      <circle cx="19" cy="6" r="2.5" />
      <circle cx="19" cy="18" r="2.5" />
      <path d="M7.5 12H12V6h4.5M12 12v6h4.5" />
    </>
  ),
  agent: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M8 13l2.5 2L8 17M13 17h4" />
    </>
  ),
  memory: <path d="M6 3h12a1 1 0 0 1 1 1v17l-7-4-7 4V4a1 1 0 0 1 1-1Z" />,
  trace: <path d="M4 6h7M4 10h4M9 10h9M7 14h6M13 18h7" />,
  ontology: (
    <>
      <rect x="9" y="3" width="6" height="5" rx="1" />
      <rect x="3" y="16" width="6" height="5" rx="1" />
      <rect x="15" y="16" width="6" height="5" rx="1" />
      <path d="M12 8v4M6 16v-4h12v4" />
    </>
  ),
  palette: (
    <>
      <circle cx="9" cy="10" r="5" />
      <circle cx="15" cy="10" r="5" />
      <circle cx="12" cy="15" r="5" />
    </>
  ),
  sidebar: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 4v16" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M5 20c0-3.6 3.1-6 7-6s7 2.4 7 6" />
    </>
  ),
};
export function Icon({ name, size = 18 }: { name: IconName; size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="var(--icon-fill)"
      stroke="var(--icon-stroke)"
      strokeWidth="1.65"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}
