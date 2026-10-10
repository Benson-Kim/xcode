import type { ReactNode } from "react";

// The side menu's line icons, keyed by menu entry and group.
const PATHS: Record<string, ReactNode> = {
  dashboard: (
    <>
      <rect x="3" y="3" width="8" height="8" rx="2" />
      <rect x="13" y="3" width="8" height="5" rx="2" />
      <rect x="13" y="10" width="8" height="11" rx="2" />
      <rect x="3" y="13" width="8" height="8" rx="2" />
    </>
  ),
  revenue: (
    <path d="M12 3v11m0 0l-4-4m4 4l4-4M4 17v2a2 2 0 002 2h12a2 2 0 002-2v-2" />
  ),
  pettycash: (
    <path d="M3 7a2 2 0 012-2h13v4M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9H5a2 2 0 01-2-2zM17 14h.01" />
  ),
  expensesGroup: <path d="M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6" />,
  recurring: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="2" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  reports: <path d="M5 20V10M11 20V4M17 20v-7M2 20h20" />,
  setupGroup: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </>
  ),
  companies: (
    <path d="M4 21V5a2 2 0 012-2h8a2 2 0 012 2v16M16 9h2a2 2 0 012 2v10M2 21h20M8 7h4M8 11h4M8 15h4" />
  ),
  vehicles: (
    <>
      <rect x="4" y="3" width="16" height="14" rx="2" />
      <path d="M4 11h16M7 17v3M17 17v3M8 14h.01M16 14h.01" />
    </>
  ),
  expenses: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
  people: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20a6.5 6.5 0 0113 0M16 4.6a3.5 3.5 0 010 6.8M18 14.2a6.5 6.5 0 013.5 5.8" />
    </>
  ),
  history: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" />
    </>
  ),
  centralexpenses: (
    <path d="M4 5a2 2 0 012-2h13v14H6a2 2 0 00-2 2V5zM4 19a2 2 0 002 2h13v-4M9 7h6M9 11h4" />
  ),
  menu: <path d="M4 6h16M4 12h16M4 18h16" />,
  chevron: <path d="M6 9l6 6 6-6" />,
};

export function NavIcon({ name }: { name: string }) {
  return (
    <svg
      width="19"
      height="19"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.9"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {PATHS[name] ?? PATHS.dashboard}
    </svg>
  );
}
