"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { PeopleAccessView } from "./PeopleAccessView";
import { OrganizationSettingsView } from "./OrganizationSettingsView";
import { PreferencesView } from "./PreferencesView";
import { Brand } from "./Brand";
import {
  CompaniesPage,
  ExpenseCategoriesPage,
  HistoryPage,
  RecurringPage,
  VehiclesPage,
} from "./setup";
import {
  Card,
  CardAction,
  CardGridSkeleton,
  CardHeader,
  CardNote,
  CardValue,
  ChevronIcon,
  Dialog,
  IconButton,
  ListSkeleton,
  MenuIcon,
  PageHeader,
  SegmentedControl,
  SubHeading,
  ToastProvider,
  cn,
} from "./ui";
import { fetchWithSession } from "../lib/session";
import {
  SessionProvider,
  useSession,
  type Session,
} from "../lib/session-context";
import { configureFormats, initials } from "../lib/format";
import { useResource } from "../lib/data";
import {
  AppearanceProvider,
  applyAppearance,
  type Appearance,
} from "../lib/appearance";
import type { PermissionGroup, View } from "../lib/types";

type NavItem = { id: View; label: string; permission?: string | string[] };

// Every menu entry names the permission that shows it, or the permissions any one of which shows it
const topLevel: NavItem[] = [
  { id: "dashboard", label: "Dashboard" },
  { id: "revenue", label: "Revenue", permission: "revenue.view" },
];
const setupGroup: NavItem[] = [
  { id: "companies", label: "PSV companies", permission: "companies.manage" },
  { id: "vehicles", label: "Vehicles", permission: "vehicles.manage" },
  {
    id: "expenses",
    label: "Expense categories",
    permission: ["expenses.setup", "expenses.view", "commitments.view"],
  },
  {
    id: "recurring",
    label: "Scheduled expenses and savings",
    permission: "commitments.view",
  },
  { id: "people", label: "People and access", permission: "people.view" },
  { id: "history", label: "Change log", permission: "audit.view" },
  {
    id: "settings",
    label: "Organization settings",
    permission: "organization.manage",
  },
];

export type ViewParams = { openItem?: string; newForVehicle?: string };

export function AppShell({ onSignOut }: { onSignOut: () => void }) {
  const [view, setView] = useState<View>("dashboard");
  const [params, setParams] = useState<ViewParams>({});
  // Bumped on every navigation so choosing a menu entry always opens that page fresh (its list, not an open editor).
  const [visit, setVisit] = useState(0);
  const [session, setSession] = useState<Session | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(true);
  const [accessOpen, setAccessOpen] = useState(false);

  useEffect(() => {
    let active = true;
    fetchWithSession("/api/auth/session")
      .then((response) =>
        response.ok
          ? response.json()
          : Promise.reject(new Error("Your session could not be loaded.")),
      )
      .then((value: Session) => active && setSession(value))
      .catch((reason: Error) => active && setSessionError(reason.message));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setMenuOpen(false);
      setUserMenuOpen(false);
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, []);

  // Branding, formats and display preferences: applied on load and again whenever a screen saves them.
  const appearance = useResource<Appearance>(
    session ? "setup/appearance" : null,
  );
  configureFormats(appearance.data?.formats);
  useEffect(() => applyAppearance(appearance.data ?? null), [appearance.data]);
  useEffect(
    () => () => {
      configureFormats(null);
      applyAppearance(null);
    },
    [],
  );
  const appearanceState = useMemo(
    () => ({
      appearance: appearance.data ?? null,
      loading: appearance.loading || !session,
      refresh: appearance.reload,
    }),
    [appearance.data, appearance.loading, appearance.reload, session],
  );
  const brand = appearance.data?.branding;

  const sessionState = useMemo(
    () => ({
      session,
      can: (permission: string) =>
        Boolean(session?.permissions.includes(permission)),
    }),
    [session],
  );
  const { can } = sessionState;
  const allowed = (item: NavItem) =>
    !item.permission || [item.permission].flat().some(can);
  const displayName = session
    ? `${session.firstName} ${session.lastName}`.trim()
    : "";

  function navigate(next: View, nextParams: ViewParams = {}) {
    setView(next);
    setParams(nextParams);
    setVisit((current) => current + 1);
    setMenuOpen(false);
    setUserMenuOpen(false);
    window.scrollTo?.(0, 0);
  }

  const navButton = (item: NavItem) => (
    <li key={item.id}>
      <button
        type="button"
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => navigate(item.id)}
        className="flex min-h-10.5 w-full items-center rounded-[10px] px-3 text-left text-[15px] hover:bg-hover aria-[current=page]:bg-blue-soft aria-[current=page]:font-bold aria-[current=page]:text-blue-dark"
      >
        {item.label}
      </button>
    </li>
  );
  const visibleSetup = setupGroup.filter(allowed);

  return (
    <SessionProvider value={sessionState}>
      <AppearanceProvider value={appearanceState}>
        <ToastProvider>
          <div className="flex min-h-screen flex-col">
            <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-card-line bg-white px-5 max-[899px]:gap-1.5 max-[899px]:pr-2 max-[899px]:pl-1">
              <IconButton
                className="hidden max-[899px]:grid"
                aria-label="Open menu"
                aria-expanded={menuOpen}
                aria-controls="main-menu"
                onClick={() => setMenuOpen((open) => !open)}
              >
                <MenuIcon />
              </IconButton>
              <Brand
                compact
                loading={appearanceState.loading && !appearance.error}
                name={brand?.displayName}
                subline={appearance.data?.organizationName}
                logo={brand?.logo}
                logoAlt={brand?.logoAlt}
              />
              <span className="flex-1" />
              <div className="relative">
                <button
                  type="button"
                  aria-haspopup="menu"
                  aria-expanded={userMenuOpen}
                  onClick={() => setUserMenuOpen((open) => !open)}
                  className="flex min-h-11 items-center gap-2.5 rounded-xl px-2 py-1 text-left hover:bg-hover"
                >
                  <span
                    aria-hidden="true"
                    className="grid size-9 shrink-0 place-items-center rounded-full bg-brand text-sm font-bold text-white"
                  >
                    {session
                      ? initials(session.firstName, session.lastName)
                      : ""}
                  </span>
                  <span className="max-[899px]:hidden">
                    <span className="block text-sm font-semibold">
                      {displayName || "Your account"}
                    </span>
                    <span className="block text-xs text-grey">
                      {session?.role || "Loading your access"}
                    </span>
                  </span>
                </button>
                {userMenuOpen && (
                  <div
                    role="menu"
                    className="absolute top-13 right-0 z-40 min-w-50 rounded-xl border border-card-line bg-white p-1.5 shadow-menu"
                  >
                    <MenuButton
                      onClick={() => {
                        setUserMenuOpen(false);
                        setAccessOpen(true);
                      }}
                    >
                      Your access
                    </MenuButton>
                    <MenuButton onClick={() => navigate("preferences")}>
                      Your preferences
                    </MenuButton>
                    <MenuButton onClick={onSignOut}>Sign out</MenuButton>
                  </div>
                )}
              </div>
            </header>
            <div className="flex min-h-0 flex-1">
              <nav
                id="main-menu"
                aria-label="Main"
                className={cn(
                  "w-62 shrink-0 overflow-y-auto border-r border-card-line bg-white px-3 py-4",
                  "max-[899px]:fixed max-[899px]:top-16 max-[899px]:bottom-0 max-[899px]:left-0 max-[899px]:z-30 max-[899px]:transition-transform motion-reduce:transition-none",
                  menuOpen
                    ? "max-[899px]:shadow-drawer"
                    : "max-[899px]:-translate-x-full",
                )}
              >
                <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
                  {topLevel.filter(allowed).map(navButton)}
                </ul>
                {visibleSetup.length > 0 && (
                  <div className="mt-3.5">
                    <button
                      type="button"
                      aria-expanded={setupOpen}
                      onClick={() => setSetupOpen((open) => !open)}
                      className="flex min-h-9 w-full items-center justify-between px-3 text-[13px] font-bold text-grey"
                    >
                      Setup
                      <ChevronIcon
                        className={cn(
                          "transition-transform motion-reduce:transition-none",
                          !setupOpen && "-rotate-90",
                        )}
                      />
                    </button>
                    {setupOpen && (
                      <ul className="m-0 flex list-none flex-col gap-0.5 p-0">
                        {visibleSetup.map(navButton)}
                      </ul>
                    )}
                  </div>
                )}
              </nav>
              {menuOpen && (
                <button
                  type="button"
                  aria-label="Close menu"
                  onClick={() => setMenuOpen(false)}
                  className="fixed inset-x-0 top-16 bottom-0 z-25 hidden bg-navy/35 max-[899px]:block"
                />
              )}
              <main className="min-w-0 flex-1 px-8 pt-7 pb-12 max-[899px]:px-4 max-[899px]:pt-5 max-[899px]:pb-10">
                <Page
                  key={visit}
                  view={view}
                  params={params}
                  sessionError={sessionError}
                  onNavigate={navigate}
                />
                <p className="mt-8 mb-0 text-xs text-grey">XCODE Web v0.9</p>
              </main>
            </div>
            <AccessDialog
              open={accessOpen}
              onClose={() => setAccessOpen(false)}
            />
          </div>
        </ToastProvider>
      </AppearanceProvider>
    </SessionProvider>
  );
}

function MenuButton({
  onClick,
  children,
}: {
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="menuitem"
      onClick={onClick}
      className="block min-h-11 w-full rounded-lg px-3 text-left text-[15px] hover:bg-hover"
    >
      {children}
    </button>
  );
}

function Page({
  view,
  params,
  sessionError,
  onNavigate,
}: {
  view: View;
  params: ViewParams;
  sessionError: string;
  onNavigate: (view: View, params?: ViewParams) => void;
}) {
  const { session, can } = useSession();
  if (view === "dashboard")
    return (
      <Dashboard session={session} error={sessionError} onOpen={onNavigate} />
    );
  if (view === "revenue")
    return <RevenueModule onBack={() => onNavigate("dashboard")} />;
  if (view === "companies") return <CompaniesPage />;
  if (view === "vehicles")
    return (
      <VehiclesPage
        onOpenRecurring={(openItem) => onNavigate("recurring", { openItem })}
        onAddRecurring={(newForVehicle) =>
          onNavigate("recurring", { newForVehicle })
        }
      />
    );
  if (view === "expenses")
    return <ExpenseCategoriesPage canManage={can("expenses.setup")} />;
  if (view === "recurring")
    return <RecurringPage canManage={can("commitments.manage")} {...params} />;
  if (view === "people")
    return <PeopleAccessView canManageAccess={can("access.manage")} />;
  if (view === "history") return <HistoryPage />;
  if (view === "settings") return <OrganizationSettingsView />;
  return <PreferencesView />;
}

const dashboardCards = [
  {
    permission: "dash.capture",
    title: "Today's revenue",
    sub: "Your vehicles, today",
    value: "KES 0",
    note: "Revenue capture data will appear here.",
    action: "Capture revenue",
    view: "revenue" as const,
    primary: true,
  },
  {
    permission: "dash.revenue",
    title: "Revenue",
    sub: "This {period}",
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
    sub: "This {period}",
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
    title: "Edited after capture",
    sub: "Records changed after they were captured",
    value: "0",
    note: "Change history will appear here.",
    action: "View change log",
    view: "history" as const,
  },
];

const periods = [
  { value: "today", label: "Today" },
  { value: "week", label: "This week" },
  { value: "month", label: "This month" },
] as const;

function Dashboard({
  session,
  error,
  onOpen,
}: {
  session: Session | null;
  error: string;
  onOpen: (view: View) => void;
}) {
  const [period, setPeriod] =
    useState<(typeof periods)[number]["value"]>("week");
  const cards = dashboardCards.filter((card) =>
    session?.permissions.includes(card.permission),
  );
  const periodLabel =
    period === "today" ? "today" : period === "week" ? "week" : "month";
  return (
    <section>
      <PageHeader
        title="Dashboard"
        description="Your fleet at a glance, based on the access you have."
      />
      <div className="mt-5 mb-6 flex flex-wrap items-center gap-3 rounded-[14px] border border-card-line bg-white p-3 max-[480px]:flex-col max-[480px]:items-stretch">
        <SegmentedControl
          label="Period"
          options={[...periods]}
          value={period}
          onChange={setPeriod}
          className="max-[480px]:grid max-[480px]:grid-cols-3 max-[480px]:self-stretch"
        />
        <span className="flex items-center gap-2 text-sm">
          <span className="text-grey">Scope</span>
          <span className="inline-flex min-h-9 items-center rounded-full bg-divider px-3 font-semibold">
            Your access
          </span>
        </span>
      </div>
      {error ? (
        <Card className="max-w-140">
          <CardHeader
            title="Your dashboard could not be loaded"
            description={error}
          />
        </Card>
      ) : !session ? (
        <CardGridSkeleton count={3} />
      ) : cards.length === 0 ? (
        <Card className="max-w-140">
          <CardHeader
            title="Nothing to show yet"
            description="Your admin decides what you can see here."
          />
        </Card>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] items-start gap-4 max-[480px]:grid-cols-1">
          {cards.map((card) => (
            <Card key={card.title} aria-labelledby={`card-${card.permission}`}>
              <CardHeader
                id={`card-${card.permission}`}
                title={card.title}
                description={card.sub.replace("{period}", periodLabel)}
              />
              <CardValue>{card.value}</CardValue>
              <CardNote>{card.note}</CardNote>
              {card.action && card.view && (
                <CardAction
                  primary={card.primary}
                  onClick={() => onOpen(card.view)}
                >
                  {card.action}
                </CardAction>
              )}
            </Card>
          ))}
        </div>
      )}
    </section>
  );
}

// Screens not built yet are shown as a card explaining why the person sees them (the design's module view).
function RevenueModule({ onBack }: { onBack: () => void }) {
  return (
    <section>
      <PageHeader title="Revenue" />
      <Card className="mt-5 max-w-140">
        <CardHeader
          title="Revenue"
          description="You see this because you can: View revenue records."
        />
        <CardNote>
          Revenue records are not available from the current API yet.
        </CardNote>
        <CardAction onClick={onBack}>Back to dashboard</CardAction>
      </Card>
    </section>
  );
}

// "Your access": the signed-in person's role and permissions, grouped as in the catalog.
function AccessDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { session } = useSession();
  const catalog = useResource<PermissionGroup[]>(
    open ? "setup/access/catalog" : null,
  );
  const mine = new Set(session?.permissions ?? []);
  return (
    <Dialog open={open} title="Your access" onClose={onClose}>
      <dl className="m-0 mb-2 grid gap-2">
        <div className="flex flex-col">
          <dt className="text-[13px] text-grey">Role</dt>
          <dd className="m-0 font-semibold">
            {session?.role || "Not assigned"}
          </dd>
        </div>
      </dl>
      {catalog.loading ? (
        <ListSkeleton rows={4} />
      ) : catalog.error ? (
        <CardNote>{catalog.error}</CardNote>
      ) : (
        catalog.data?.map((group) => {
          const items = group.items.filter((item) => mine.has(item.key));
          if (!items.length) return null;
          return (
            <div key={group.name}>
              <SubHeading>{group.name}</SubHeading>
              <ul className="m-0 list-disc pl-5">
                {items.map((item) => (
                  <li key={item.key} className="py-0.75 text-[15px]">
                    {item.label}
                  </li>
                ))}
              </ul>
            </div>
          );
        })
      )}
    </Dialog>
  );
}
