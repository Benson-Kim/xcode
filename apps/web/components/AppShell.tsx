"use client";

import { useEffect, useState } from "react";
import { PeopleAccessView } from "./PeopleAccessView";
import { OrganizationSettingsView } from "./OrganizationSettingsView";
import { requestSetup } from "./requestSetup";
import {
  CompaniesView,
  HistoryView,
  RecurringView,
  VehiclesView,
} from "./SetupViews";
import type { Page, View } from "./setupTypes";

const navigation: { id: View; label: string }[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "revenue", label: "Revenue" },
  { id: "people", label: "People and access" },
  { id: "companies", label: "PSV companies" },
  { id: "vehicles", label: "Vehicles" },
  { id: "recurring", label: "Recurring costs and savings" },
  { id: "history", label: "Change log" },
  { id: "settings", label: "Organization settings" },
];

export function AppShell({ onSignOut }: { onSignOut: () => void }) {
  const [view, setView] = useState<View>("dashboard");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [period, setPeriod] = useState("week");
  type Session = {
    firstName: string;
    lastName: string;
    role: string;
    permissions: string[];
  };
  const [session, setSession] = useState<Session>({
    firstName: "",
    lastName: "",
    role: "",
    permissions: [],
  });
  useEffect(() => {
    fetch("/api/auth/session")
      .then((response) =>
        response.ok
          ? response.json()
          : Promise.reject(new Error("Session expired.")),
      )
      .then((value: Session) => setSession(value))
      .catch((reason: Error) => setError(reason.message));
  }, []);
  const permissions = session.permissions;
  const displayName =
    [session.firstName, session.lastName].filter(Boolean).join(" ") ||
    "Your account";
  const visibleNavigation = navigation.filter(
    (item) =>
      item.id === "dashboard" ||
      (item.id === "revenue" && permissions.includes("revenue.view")) ||
      (item.id === "people" && permissions.includes("people.view")) ||
      (item.id === "companies" && permissions.includes("companies.manage")) ||
      (item.id === "vehicles" && permissions.includes("vehicles.manage")) ||
      (item.id === "recurring" && permissions.includes("commitments.view")) ||
      (item.id === "history" && permissions.includes("audit.view")) ||
      (item.id === "settings" && permissions.includes("organization.manage")),
  );
  useEffect(() => {
    if (["dashboard", "revenue", "people", "settings"].includes(view)) return;
    const path =
      view === "companies"
        ? "companies"
        : view === "vehicles"
          ? "vehicles"
          : view === "recurring"
            ? "recurring"
            : "history";
    requestSetup<Page<Record<string, unknown>>>(path)
      .then((page) => setRows(page.items))
      .catch((reason: Error) => setError(reason.message));
  }, [view]);
  function openView(next: View) {
    setView(next);
    setMenuOpen(false);
    setUserMenuOpen(false);
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <button
          className="icon-btn menu-btn"
          aria-label="Open menu"
          aria-expanded={menuOpen}
          onClick={() => setMenuOpen((open) => !open)}
        >
          ☰
        </button>
        <span className="tb-brand">
          <span className="brand-mark" aria-hidden="true">
            ⌁
          </span>
          <span>
            <span className="brand-name">XCODE</span>
            <span className="brand-sub">Fleet finance</span>
          </span>
        </span>
        <span className="spacer" />
        <label className="demo-as">
          <span>Demo: view as</span>
          <select aria-label="Demo: view as" defaultValue="current">
            <option value="current">{session.role || "Current access"}</option>
            <option value="owner">Owner</option>
            <option value="admin">Office admin</option>
            <option value="manager">Fleet manager</option>
            <option value="clerk">Revenue clerk</option>
          </select>
        </label>
        <div className="user-wrap">
          <button
            className="user-btn"
            aria-expanded={userMenuOpen}
            onClick={() => setUserMenuOpen((open) => !open)}
          >
            <span className="avatar-sm">{displayName.slice(0, 1)}</span>
            <span className="user-text">
              <span className="user-name">{displayName}</span>
              <span className="user-role">
                {session.role || "Organization access"}
              </span>
            </span>
          </button>
          {userMenuOpen && (
            <div className="user-menu">
              <button onClick={() => setUserMenuOpen(false)}>
                Your access
              </button>
              <button onClick={onSignOut}>Sign out</button>
            </div>
          )}
        </div>
      </header>
      <div className="app-body">
        <aside
          className={`sidebar ${menuOpen ? "open" : ""}`}
          aria-label="Main navigation"
        >
          <nav>
            <button className="nav-group-btn" aria-expanded="true">
              Overview
            </button>
            {visibleNavigation
              .filter(
                (item) => item.id === "dashboard" || item.id === "revenue",
              )
              .map((item) => (
                <button
                  className="nav-item"
                  aria-current={view === item.id ? "page" : undefined}
                  key={item.id}
                  onClick={() => openView(item.id)}
                >
                  {item.label}
                </button>
              ))}
            <button className="nav-group-btn" aria-expanded="true">
              Setup
            </button>
            {visibleNavigation
              .filter((item) => !["dashboard", "revenue"].includes(item.id))
              .map((item) => (
                <button
                  className="nav-item"
                  aria-current={view === item.id ? "page" : undefined}
                  key={item.id}
                  onClick={() => openView(item.id)}
                >
                  {item.label}
                </button>
              ))}
          </nav>
        </aside>
        {menuOpen && (
          <button
            className="scrim"
            aria-label="Close menu"
            onClick={() => setMenuOpen(false)}
          />
        )}
        <main className="content">
            {view === "dashboard" && (
              <>
                <h1 className="page-title">Dashboard</h1>
                <p className="page-sub">Your fleet at a glance, based on the access you have.</p>
              </>
            )}
          {error && (
            <p className="error-box" role="alert">
              {error}
            </p>
          )}
          {view === "people" ? (
            <PeopleAccessView />
          ) : view === "dashboard" ? (
            <Dashboard
              permissions={permissions}
              period={period}
              onPeriodChange={setPeriod}
              onOpen={openView}
            />
          ) : (
            <ResourceView view={view} rows={rows} error="" />
          )}
        </main>
      </div>
    </div>
  );
}

function Dashboard({
  permissions,
  period,
  onPeriodChange,
  onOpen,
}: {
  permissions: string[];
  period: string;
  onPeriodChange: (period: string) => void;
  onOpen: (view: View) => void;
}) {
  const cards = [
    {
      permission: "dash.capture",
      title: "Today's revenue",
      sub: "Your vehicles, today",
      value: "KES 0",
      note: "Revenue capture data will appear here.",
      action: "Capture revenue",
      view: "revenue" as const,
    },
    {
      permission: "dash.revenue",
      title: "Revenue",
      sub: `This ${period}`,
      value: "KES 0",
      note: "No revenue records are available yet.",
    },
    {
      permission: "dash.net",
      title: "Net contribution",
      sub: "Revenue less all costs",
      value: "KES 0",
      note: "Cost and revenue data will appear here.",
    },
    {
      permission: "dash.costs",
      title: "Costs",
      sub: `This ${period}`,
      value: "KES 0",
      note: "Cost totals are waiting for records.",
    },
    {
      permission: "dash.gaps",
      title: "Missing revenue days",
      sub: "No record and no reason",
      value: "0 days",
      note: "No gaps are available yet.",
      action: "Open revenue",
      view: "revenue" as const,
    },
    {
      permission: "dash.commitments",
      title: "Renewals due",
      sub: "Upcoming commitments",
      value: "0",
      note: "Renewal data will appear here.",
    },
    {
      permission: "dash.edits",
      title: "Recent changes",
      sub: "Edited after capture",
      value: "0",
      note: "Change history will appear here.",
      action: "View change log",
      view: "history" as const,
    },
  ].filter((card) => permissions.includes(card.permission));
  return (
    <section>
      <div className="filterbar">
        <div className="seg" role="group" aria-label="Period">
          {["today", "week", "month"].map((option) => (
            <button
              key={option}
              aria-pressed={period === option}
              onClick={() => onPeriodChange(option)}
            >
              {option === "today"
                ? "Today"
                : option === "week"
                  ? "This week"
                  : "This month"}
            </button>
          ))}
        </div>
        <div className="scope">
          <span>Scope</span>
          <span className="scope-chip">Your access</span>
        </div>
      </div>
      <div className="cards">
        {cards.map((card) => (
          <article className="card" key={card.title}>
            <header>
              <h2 className="card-title">{card.title}</h2>
              <p className="card-sub">{card.sub}</p>
            </header>
            <p className="card-value">{card.value}</p>
            <p className="card-note">{card.note}</p>
            {card.action && card.view && (
              <button
                className={`card-action ${card.title === "Today's revenue" ? "primary" : ""}`}
                onClick={() => onOpen(card.view)}
              >
                {card.action}
              </button>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

function ResourceView({
  view,
  rows,
  error,
}: {
  view: View;
  rows: Record<string, unknown>[];
  error: string;
}) {
  const title = navigation.find((item) => item.id === view)?.label;
  if (view === "companies") return <CompaniesView />;
  if (view === "vehicles") return <VehiclesView />;
  if (view === "recurring") return <RecurringView />;
  if (view === "history") return <HistoryView />;
  if (view === "settings") return <OrganizationSettingsView />;
  if (view === "revenue")
    return (
      <section className="module">
        <article className="card">
          <header>
            <h2 className="card-title">Revenue</h2>
            <p className="card-sub">
              Daily capture and performance against expected revenue.
            </p>
          </header>
          <p className="card-note">
            Revenue records are not available from the current API yet.
          </p>
          <button className="card-action primary" disabled>
            Capture revenue
          </button>
        </article>
      </section>
    );
  return (
    <section>
      <p className="eyebrow">Organization administration</p>
      <h1>{title}</h1>
      {error ? (
        <p className="error-box" role="alert">
          {error}
        </p>
      ) : rows.length ? (
        <div className="table-card">
          <table className="list">
            <tbody>
              {rows.map((row, index) => (
                <tr key={index}>
                  {Object.values(row)
                    .slice(0, 4)
                    .map((value, cell) => (
                      <td key={cell}>{String(value)}</td>
                    ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <article className="card empty-state">
          <h2 className="card-title">No records yet</h2>
          <p className="card-note">
            This screen is ready for {title?.toLowerCase()} data when the API
            provides it.
          </p>
        </article>
      )}
    </section>
  );
}
