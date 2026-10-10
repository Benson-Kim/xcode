"use client";

import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
  type ReactNode,
} from "react";

import {
  createFormatter,
  initials,
  percentText,
  plural,
  type Formatter,
} from "@xcode/shared/format";
import {
  canSee,
  NAV,
  NAV_SECTIONS,
  permissionChecker,
  startsOnToday,
  type DashboardKey,
  type NavId,
  type NavSection,
  type PermissionCheck,
  type PermissionKey,
} from "@xcode/shared/permissions";
import {
  canOpenPettyCash,
  type PettyCashDashboard,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";
import {
  REVENUE_PERIODS,
  revenuePeriodLabel,
  type RevenueDashboard,
  type RevenuePeriod,
} from "@xcode/shared/revenue";

import {
  AppearanceProvider,
  applyAppearance,
  type Appearance,
} from "../lib/appearance";
import { useResource } from "../lib/data";
import { FormatsContext, useFormats } from "../lib/formats";
import { fetchWithSession } from "../lib/session";
import {
  SessionProvider,
  useSession,
  type Session,
} from "../lib/session-context";
import type { MyScope, PermissionGroup, View } from "../lib/types";
import { Brand } from "./Brand";
import {
  approvalsFigures,
  floatFigures,
  type PettyCashCardFigures,
} from "./pettycash/dashboardCards";
import { shiftDate } from "./revenueFormat";
import type { HeroSlots } from "./ui";
import {
  Banner,
  Button,
  Card,
  CardAction,
  CardGridSkeleton,
  CardHeader,
  CardList,
  CardListItem,
  CardNote,
  CardValue,
  Dialog,
  FormActions,
  ListSkeleton,
  LoadingRegion,
  BandStats,
  HeroBand,
  HeroSlotsProvider,
  NavIcon,
  PageHeader,
  ProgressBar,
  SegmentedControl,
  Skeleton,
  StatusBadge,
  SubHeading,
  ToastProvider,
  cn,
} from "./ui";

// React keeps a failed lazy import for good, so each screen that failed to load leaves a fresh import here. Trying
// again, or opening another page, swaps them in; never a render, which would retry in a loop while offline.
const failedScreens = new Set<() => void>();
function retryFailedScreens() {
  failedScreens.forEach((retry) => retry());
  failedScreens.clear();
}

// Each screen but the dashboard loads the first time it is opened, so the first load holds only the shell and the
// dashboard. React.lazy rather than next/dynamic: in the app router next/dynamic is this same lazy and Suspense pair,
// and plain lazy runs the same way under the tests.
function lazyScreen<P extends object>(load: () => Promise<ComponentType<P>>) {
  const attempt = (): ComponentType<P> =>
    lazy(() =>
      load().then(
        (screen) => ({ default: screen }),
        (reason: unknown) => {
          failedScreens.add(() => (Loaded = attempt()));
          throw reason;
        },
      ),
    );
  let Loaded = attempt();
  return function Screen(props: P) {
    return <Loaded {...props} />;
  };
}

const RevenuePage = lazyScreen(() =>
  import("./RevenuePage").then((module) => module.RevenuePage),
);
const PettyCashPage = lazyScreen(() =>
  import("./pettycash/PettyCashPage").then((module) => module.PettyCashPage),
);
const PeopleAccessView = lazyScreen(() =>
  import("./PeopleAccessView").then((module) => module.PeopleAccessView),
);
const OrganizationSettingsView = lazyScreen(() =>
  import("./OrganizationSettingsView").then(
    (module) => module.OrganizationSettingsView,
  ),
);
const CentralExpensesPage = lazyScreen(() =>
  import("./expenses/CentralExpensesPage").then(
    (module) => module.CentralExpensesPage,
  ),
);
const ReportsPage = lazyScreen(() =>
  import("./reports/ReportsPage").then((module) => module.ReportsPage),
);
const PreferencesView = lazyScreen(() =>
  import("./PreferencesView").then((module) => module.PreferencesView),
);
const CompaniesPage = lazyScreen(() =>
  import("./setup/CompaniesPage").then((module) => module.CompaniesPage),
);
const VehiclesPage = lazyScreen(() =>
  import("./setup/VehiclesPage").then((module) => module.VehiclesPage),
);
const ExpenseCategoriesPage = lazyScreen(() =>
  import("./setup/ExpenseCategoriesPage").then(
    (module) => module.ExpenseCategoriesPage,
  ),
);
const RecurringPage = lazyScreen(() =>
  import("./setup/RecurringPage").then((module) => module.RecurringPage),
);
const HistoryPage = lazyScreen(() =>
  import("./setup/HistoryPage").then((module) => module.HistoryPage),
);

// A screen's code that did not download: what Turbopack throws (a ChunkLoadError, "Failed to load chunk …"), what
// webpack throws ("Loading chunk … failed") and what the browsers' own import() rejects with.
function isLoadFailure(error: unknown) {
  return (
    error instanceof Error &&
    (error.name === "ChunkLoadError" ||
      /Loading chunk|Failed to load chunk|dynamically imported module|Importing a module script failed/i.test(
        error.message,
      ))
  );
}

// After Try again, moves focus to the page's heading once it shows, or to its placeholder while it loads, rather than
// leaving keyboard and screen-reader users on the page body.
function FocusPage() {
  useEffect(() => {
    // The title is in the brand zone, above the sheet.
    const target =
      document.querySelector<HTMLElement>("h1") ??
      document.querySelector<HTMLElement>('main [role="status"]');
    if (!target) return;
    target.tabIndex = -1;
    target.focus();
  }, []);
  return null;
}

// Opens one page: placeholders while its code loads (each screen shows its own as soon as it has loaded, so until
// then only its title's), and a problem inside the page if it fails, with the header and menu still working. Try again
// renders it afresh, importing again a screen that did not download; a reload picks up a new release. React and
// Next.js log each error caught here to the console.
class PageBoundary extends Component<
  { children: ReactNode },
  { problem: "load" | "other" | null; retried: boolean }
> {
  state: { problem: "load" | "other" | null; retried: boolean } = {
    problem: null,
    retried: false,
  };

  static getDerivedStateFromError(error: unknown) {
    return { problem: isLoadFailure(error) ? "load" : "other" };
  }

  render() {
    const { problem, retried } = this.state;
    if (!problem)
      return (
        <Suspense
          fallback={
            <>
              {retried && <FocusPage />}
              <LoadingRegion label="Loading the page">
                <Skeleton className="h-8 w-1/3" />
              </LoadingRegion>
            </>
          }
        >
          {this.props.children}
          {retried && <FocusPage />}
        </Suspense>
      );
    return (
      <section>
        <Banner>
          {problem === "load"
            ? "This page could not be loaded. Check your connection and try again."
            : "Something went wrong on this page."}
        </Banner>
        <FormActions className="mt-4">
          <Button
            // A retry that failed again keeps focus on Try again.
            autoFocus={retried}
            onClick={() => {
              retryFailedScreens();
              this.setState({ problem: null, retried: true });
            }}
          >
            Try again
          </Button>
          {/* Offline, a reload would lose the app, not bring the page back. */}
          {navigator.onLine && (
            <Button tone="outline" onClick={() => window.location.reload()}>
              Reload the app
            </Button>
          )}
        </FormActions>
      </section>
    );
  }
}

// The pages the menu opens: the shared View, and Petty cash, which has no entry there.
type ShellView = View | "pettycash";

type NavItem = {
  id: ShellView;
  label: string;
  any?: readonly PermissionKey[];
};

// Every menu entry is shown to the people holding any of its permissions, as @xcode/shared/permissions says.
const navItems = (ids: readonly NavId[]): NavItem[] =>
  ids.map((id) => ({ id, ...NAV[id] }));

export type ViewParams = {
  openItem?: string;
  newForVehicle?: string;
  status?: PettyCashStatus;
  date?: string;
};

export function AppShell({ onSignOut }: { onSignOut: () => void }) {
  const [view, setView] = useState<ShellView>("dashboard");
  const [params, setParams] = useState<ViewParams>({});
  // Bumped on every navigation so choosing a menu entry always opens that page fresh (its list, not an open editor).
  const [visit, setVisit] = useState(0);
  const [session, setSession] = useState<Session | null>(null);
  const [sessionError, setSessionError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [accessOpen, setAccessOpen] = useState(false);
  const [mini, setMini] = useState(false);

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
  const formatter = useMemo(
    () => createFormatter(appearance.data?.formats),
    [appearance.data?.formats],
  );
  useEffect(() => applyAppearance(appearance.data ?? null), [appearance.data]);
  useEffect(
    () => () => {
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
      can: permissionChecker(session?.permissions ?? []),
    }),
    [session],
  );
  const { can } = sessionState;
  const displayName = session
    ? `${session.firstName} ${session.lastName}`.trim()
    : "";

  function navigate(next: ShellView, nextParams: ViewParams = {}) {
    retryFailedScreens();
    setView(next);
    setParams(nextParams);
    setVisit((current) => current + 1);
    setMenuOpen(false);
    setUserMenuOpen(false);
    window.scrollTo?.(0, 0);
  }

  const profile = (
    <UserMenu
      session={session}
      displayName={displayName}
      open={userMenuOpen}
      onToggle={() => setUserMenuOpen((open) => !open)}
      onAccess={() => {
        setUserMenuOpen(false);
        setAccessOpen(true);
      }}
      onPreferences={() => navigate("preferences")}
      onSignOut={onSignOut}
    />
  );
  return (
    <FormatsContext.Provider value={formatter}>
      <SessionProvider value={sessionState}>
        <AppearanceProvider value={appearanceState}>
          <ToastProvider>
            <div className={cn("app", mini && "mini", menuOpen && "drawer")}>
              <MainMenu
                view={view}
                can={can}
                onNavigate={navigate}
                onMini={() => setMini((current) => !current)}
                brand={
                  <Brand
                    compact
                    loading={appearanceState.loading && !appearance.error}
                    name={brand?.displayName}
                    subline={appearance.data?.organizationName}
                    logo={brand?.logo}
                    logoAlt={brand?.logoAlt}
                  />
                }
              />
              <Frame
                menuOpen={menuOpen}
                onMenu={() => setMenuOpen((open) => !open)}
                profile={profile}
              >
                {/* Keyed on the visit, so a screen still loading shows placeholders, never the page it replaced, and a
                  page that failed to load is left behind on the next one. */}
                <PageBoundary key={visit}>
                  <Page
                    view={view}
                    params={params}
                    sessionError={sessionError}
                    onNavigate={navigate}
                  />
                </PageBoundary>
              </Frame>
              {menuOpen && (
                <button
                  type="button"
                  aria-label="Close menu"
                  onClick={() => setMenuOpen(false)}
                  className="scrim"
                />
              )}
              <AccessDialog
                open={accessOpen}
                onClose={() => setAccessOpen(false)}
              />
            </div>
          </ToastProvider>
        </AppearanceProvider>
      </SessionProvider>
    </FormatsContext.Provider>
  );
}

// The brand zone (title, actions, profile, headline card) over the working sheet, with the slots pages draw into.
function Frame({
  menuOpen,
  onMenu,
  profile,
  children,
}: {
  menuOpen: boolean;
  onMenu: () => void;
  profile: ReactNode;
  children: ReactNode;
}) {
  const [title, setTitle] = useState<HTMLElement | null>(null);
  const [actions, setActions] = useState<HTMLElement | null>(null);
  const [band, setBand] = useState<HTMLElement | null>(null);
  const [headHidden, setHeadHidden] = useState(false);
  const slots: HeroSlots = {
    title,
    actions,
    band,
    profile,
    hideHead: setHeadHidden,
  };
  const menuToggle = (
    <button
      type="button"
      className="menu-m"
      aria-label="Open menu"
      aria-expanded={menuOpen}
      aria-controls="main-menu"
      onClick={onMenu}
    >
      <NavIcon name="menu" />
    </button>
  );
  return (
    <HeroSlotsProvider value={slots}>
      <main className="main">
        <section className="hero">
          {/* A headline card that carries the actions takes the title row's place; its title stays for screen readers. */}
          <div className={cn("head", headHidden && "sr-only")}>
            {!headHidden && menuToggle}
            <div ref={setTitle} className="ht" />
            <div className="acts">
              <div ref={setActions} className="contents" />
              {!headHidden && profile}
            </div>
          </div>
          <div className="hrow">
            {headHidden && menuToggle}
            <div ref={setBand} className="contents" />
          </div>
        </section>
        <div className="pagebody">{children}</div>
      </main>
    </HeroSlotsProvider>
  );
}

// The side menu: each section in order, a group collapsible like Setup, and only the entries this person may open.
// On a desk screen it collapses to icons; on a phone it is a drawer.
function MainMenu({
  view,
  can,
  brand,
  onNavigate,
  onMini,
}: {
  view: ShellView;
  can: PermissionCheck;
  brand: ReactNode;
  onNavigate: (view: ShellView) => void;
  onMini: () => void;
}) {
  const [closedGroups, setClosedGroups] = useState<ReadonlySet<string>>(
    new Set(),
  );
  const allowed = (item: NavItem) => canSee(item, can);
  const navButton = (item: NavItem, sub: boolean) => (
    <li key={item.id}>
      <button
        type="button"
        title={item.label}
        aria-current={view === item.id ? "page" : undefined}
        onClick={() => onNavigate(item.id)}
        className={cn("ni", sub && "sub")}
      >
        <NavIcon name={item.id} />
        <span className="lb">{item.label}</span>
      </button>
    </li>
  );
  const toggleGroup = (id: string) =>
    setClosedGroups((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  const navSection = (section: NavSection, index: number) => {
    const visible = navItems(section.items).filter(allowed);
    if (!visible.length) return null;
    if (section.kind === "items")
      return (
        <ul key={index} className="kids m-0 list-none p-0">
          {visible.map((item) => navButton(item, false))}
        </ul>
      );
    const open = !closedGroups.has(section.id);
    return (
      <div key={section.id} className="kids">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => toggleGroup(section.id)}
          className="ni grp"
        >
          <NavIcon name={`${section.id}Group`} />
          <span className="lb">{section.label}</span>
          <span className="chev">
            <NavIcon name="chevron" />
          </span>
        </button>
        {open && (
          <ul className="kids m-0 list-none p-0">
            {visible.map((item) => navButton(item, true))}
          </ul>
        )}
      </div>
    );
  };

  return (
    <nav id="main-menu" aria-label="Main" className="nav">
      <div className="brandrow">
        {brand}
        <button
          type="button"
          className="navbtn"
          aria-label="Collapse or expand menu"
          title="Collapse or expand menu"
          onClick={onMini}
        >
          <NavIcon name="menu" />
        </button>
      </div>
      {NAV_SECTIONS.map(navSection)}
      <div className="ver">XCODE Web v2.28</div>
    </nav>
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
      className="block min-h-10 w-full rounded-[9px] px-3 text-left font-semibold text-ink hover:bg-paper"
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
  view: ShellView;
  params: ViewParams;
  sessionError: string;
  onNavigate: (view: ShellView, params?: ViewParams) => void;
}) {
  const { session, can } = useSession();
  if (view === "dashboard")
    return (
      <Dashboard session={session} error={sessionError} onOpen={onNavigate} />
    );
  if (view === "revenue") return <RevenuePage />;
  if (view === "centralexpenses")
    return (
      <CentralExpensesPage
        onOpenPettyCash={(date) => onNavigate("pettycash", { date })}
      />
    );
  if (view === "reports") return <ReportsPage />;
  if (view === "pettycash")
    return (
      <PettyCashPage initialStatus={params.status} initialDate={params.date} />
    );
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

type Period = RevenuePeriod;

// One dashboard card. A card whose data is not connected yet says so rather than showing zeros.
type DashboardCard = {
  permission: DashboardKey;
  title: string;
  sub: string;
  value?: string;
  bad?: boolean;
  bar?: number;
  note?: string;
  list?: PettyCashCardFigures["list"];
  busy?: boolean;
  unavailable?: boolean;
  action?: {
    label: string;
    view: ShellView;
    params?: ViewParams;
    primary?: boolean;
  };
};
type Figures = { data?: RevenueDashboard; error: string };
type PettyFigures = { data?: PettyCashDashboard; error: string };
// What the figures decide: the value and its note, and whether the card's action still applies.
type Shown = Pick<DashboardCard, "value" | "bad" | "bar" | "note" | "action">;

// "Today, 30 Sep 2026", "This week, 28 Sep to 4 Oct 2026", "This month, 1 to 30 Sep 2026", from the business date.
function periodLabel(
  formats: Formatter,
  period: Period,
  data?: RevenueDashboard,
) {
  const name = revenuePeriodLabel(period);
  if (!data) return name;
  if (period === "today")
    return `${name}, ${formats.formatDateOnly(data.from)}`;
  return `${name}, ${formats.formatDateRange(data.from, period === "week" ? shiftDate(data.from, 6) : data.through)}`;
}

// A card from the revenue dashboard: placeholders while it loads, the error if it failed, and only the figures the
// server sent, which leaves out (null) anything the viewer may not see.
function revenueCard(
  card: Omit<DashboardCard, Exclude<keyof Shown, "action">>,
  figures: Figures,
  show: (data: RevenueDashboard) => Shown,
): DashboardCard {
  if (figures.error) return { ...card, note: figures.error };
  if (!figures.data) return { ...card, busy: true };
  return { ...card, ...show(figures.data) };
}

// A card from the petty cash dashboard: null once loaded when the server withholds it from this person.
function pettyCashCard(
  card: Pick<DashboardCard, "permission" | "title" | "sub">,
  figures: PettyFigures,
  canOpen: boolean,
  show: (data: PettyCashDashboard) => PettyCashCardFigures | null,
  actionLabel: (shown: PettyCashCardFigures) => string | null,
): DashboardCard | null {
  if (figures.error) return { ...card, note: figures.error };
  if (!figures.data) return { ...card, busy: true };
  const shown = show(figures.data);
  if (!shown) return null;
  const label = canOpen ? actionLabel(shown) : null;
  return {
    ...card,
    value: shown.value,
    bad: shown.bad,
    note: shown.note,
    list: shown.list,
    action: label
      ? {
          label,
          view: "pettycash",
          params: shown.status ? { status: shown.status } : undefined,
          primary: true,
        }
      : undefined,
  };
}

const unavailable = (
  permission: DashboardKey,
  title: string,
  sub: string,
  note: string,
): DashboardCard => ({
  permission,
  title,
  sub,
  note,
  unavailable: true,
});

// The cards in the design's order, each shown to the people with its permission.
function dashboardCards(
  formats: Formatter,
  can: PermissionCheck,
  period: Period,
  selected: Figures,
  month: Figures,
  petty: PettyFigures,
  canOpenPetty: boolean,
) {
  const label = periodLabel(formats, period, selected.data);
  const floatCard = pettyCashCard(
    {
      permission: "dash.float",
      title: "My petty cash float",
      sub: "Cash in hand now",
    },
    petty,
    canOpenPetty,
    (data) => data.float && floatFigures(formats, data.float),
    () => "Open petty cash",
  );
  const approvalsCard = pettyCashCard(
    {
      permission: "dash.pettycash",
      title: "Petty cash to approve",
      sub: "All managers",
    },
    petty,
    canOpenPetty,
    (data) => data.approvals && approvalsFigures(formats, data.approvals),
    (shown) => (shown.status ? "Review entries" : null),
  );
  const today = selected.data?.businessDate ?? month.data?.businessDate;
  const monthData = month.data;
  const yesterday = monthData && shiftDate(monthData.businessDate, -1);
  const fillGaps: DashboardCard["action"] =
    can("revenue.capture") || can("revenue.correct")
      ? { label: "Fill the gaps", view: "revenue" }
      : undefined;
  const cards: DashboardCard[] = [
    revenueCard(
      {
        permission: "dash.capture",
        title: "Today's revenue",
        sub: today
          ? `Your vehicles, ${formats.formatDateOnly(today)}`
          : "Your vehicles, today",
        action: { label: "Capture revenue", view: "revenue", primary: true },
      },
      selected,
      ({ capturedToday: captured, vehiclesToday: vehicles }) => {
        if (captured === null || vehicles === null) return {};
        if (vehicles === 0)
          return { note: "None of your vehicles is in the fleet today." };
        const pending = vehicles - captured;
        return {
          value: `${captured} of ${vehicles} captured`,
          note:
            pending > 0
              ? `${plural(pending, "vehicle", "vehicles")} still to capture`
              : "Every vehicle has a record for today.",
        };
      },
    ),
    ...(floatCard ? [floatCard] : []),
    revenueCard(
      { permission: "dash.revenue", title: "Revenue", sub: label },
      selected,
      ({ revenue, expected, percent, capturedToday, vehiclesToday }) => {
        if (revenue === null) return {};
        const soFar =
          period !== "month" && capturedToday !== null && vehiclesToday
            ? `. ${capturedToday} of ${vehiclesToday} vehicles have a record so far.`
            : "";
        if (percent === null)
          return {
            value: revenue ? formats.kes(revenue) : undefined,
            note: `No weekly target applies in this period${soFar || "."}`,
          };
        return {
          value: formats.kes(revenue),
          bar: percent,
          note: `${percentText(percent)} of target ${formats.kes(expected ?? 0)}, from each vehicle’s weekly target${soFar || "."}`,
        };
      },
    ),
    unavailable(
      "dash.net",
      "Net contribution",
      `Revenue less all costs. ${label}`,
      "Needs cost totals, which are not connected yet.",
    ),
    unavailable(
      "dash.costs",
      "Money out",
      `${label}. Fuel and crew pay are not tracked; revenue is recorded net of them.`,
      "Cost totals are not connected yet.",
    ),
    revenueCard(
      {
        permission: "dash.gaps",
        title: "Missing revenue days",
        // This month up to yesterday: today is not a gap before it is captured.
        sub:
          monthData && yesterday
            ? monthData.from <= yesterday
              ? `${formats.formatDateRange(monthData.from, yesterday)}. No record and no reason.`
              : "No record and no reason."
            : "This month. No record and no reason.",
        action: fillGaps,
      },
      month,
      ({ missingDays, missingVehicles }) =>
        missingDays === null
          ? {}
          : {
              value: plural(missingDays, "day", "days"),
              bad: missingDays > 0,
              // With no gaps there is nothing to fill.
              action: missingDays > 0 ? fillGaps : undefined,
              note: missingDays
                ? `${missingVehicles === null ? "" : `On ${plural(missingVehicles, "vehicle", "vehicles")}. `}Always this month, whatever period you pick.`
                : "Every vehicle has a record for every day.",
            },
    ),
    ...(approvalsCard ? [approvalsCard] : []),
    unavailable(
      "dash.commitments",
      "Yearly items due",
      "Next 30 days",
      "Yearly items are not connected yet.",
    ),
    unavailable(
      "dash.investment",
      "Money invested",
      "Against what has come back",
      "What has come back is not connected yet.",
    ),
    revenueCard(
      {
        permission: "dash.edits",
        title: "Edited after capture",
        sub: label,
        action: can("audit.view")
          ? { label: "View change log", view: "history" }
          : undefined,
      },
      selected,
      ({ editedRecords }) =>
        editedRecords === null
          ? {}
          : {
              value: plural(editedRecords, "record", "records"),
              note: editedRecords
                ? undefined
                : "Nothing was changed after capture in this period.",
            },
    ),
  ];
  return cards.filter((card) => can(card.permission));
}

function Dashboard({
  session,
  error,
  onOpen,
}: {
  session: Session | null;
  error: string;
  onOpen: (view: ShellView, params?: ViewParams) => void;
}) {
  const { can } = useSession();
  const formats = useFormats();
  const [chosen, setChosen] = useState<Period | null>(null);
  // A capturer starts on today and everyone else on the month, as in the design.
  const period: Period = chosen ?? (startsOnToday(can) ? "today" : "month");
  const periodCards = (
    ["dash.capture", "dash.revenue", "dash.edits"] as const
  ).some(can);
  // Missing days always cover the month, so the month is asked for once and shared when it is also the period.
  const byPeriod = useResource<RevenueDashboard>(
    periodCards && period !== "month"
      ? `setup/revenue/dashboard?period=${period}`
      : null,
  );
  const byMonth = useResource<RevenueDashboard>(
    can("dash.gaps") || (periodCards && period === "month")
      ? "setup/revenue/dashboard?period=month"
      : null,
  );
  const pettyCash = useResource<PettyCashDashboard>(
    can("dash.float") || can("dash.pettycash")
      ? "setup/pettycash/dashboard"
      : null,
  );
  const cards = dashboardCards(
    formats,
    can,
    period,
    period === "month" ? byMonth : byPeriod,
    byMonth,
    pettyCash,
    canOpenPettyCash(session?.permissions ?? []),
  );
  return (
    <section>
      <PageHeader
        title="Dashboard"
        description="Your fleet at a glance, based on the access you have."
      />
      <HeroBand
        period={
          <SegmentedControl
            label="Period"
            options={[...REVENUE_PERIODS]}
            value={period}
            onChange={setChosen}
            className="max-[480px]:grid max-[480px]:grid-cols-3 max-[480px]:self-stretch"
          />
        }
      >
        <BandStats items={[{ label: "Scope", value: "Your access" }]} />
      </HeroBand>
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
        <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] items-start gap-[18px] max-[480px]:grid-cols-1">
          {cards.map((card) => {
            const action = card.action;
            return (
              <Card
                key={card.permission}
                aria-labelledby={`card-${card.permission}`}
                aria-busy={card.busy || undefined}
              >
                <CardHeader
                  id={`card-${card.permission}`}
                  title={card.title}
                  description={card.sub}
                />
                {card.busy ? (
                  <>
                    <Skeleton className="mt-2 h-8 w-3/5" />
                    <Skeleton className="h-3 w-4/5" />
                  </>
                ) : card.unavailable ? (
                  <p className="m-0">
                    <StatusBadge>Not available yet</StatusBadge>
                  </p>
                ) : (
                  card.value && (
                    <CardValue tone={card.bad ? "bad" : undefined}>
                      {card.value}
                    </CardValue>
                  )
                )}
                {card.bar !== undefined && <ProgressBar value={card.bar} />}
                {card.note && <CardNote>{card.note}</CardNote>}
                {card.list && card.list.length > 0 && (
                  <CardList>
                    {card.list.map((row) => (
                      <CardListItem
                        key={row.id}
                        left={row.left}
                        leftSub={row.leftSub}
                        right={row.right}
                        rightSub={row.rightSub}
                      />
                    ))}
                  </CardList>
                )}
                {action && (
                  <CardAction
                    primary={action.primary}
                    onClick={() => onOpen(action.view, action.params)}
                  >
                    {action.label}
                  </CardAction>
                )}
              </Card>
            );
          })}
        </div>
      )}
    </section>
  );
}

// The companies the server says this person reaches: named while there are few enough to read, counted
// after that. An organization-wide viewer sees "All companies" and no vehicle count, as in the people list.
function myScopeLabel(scope?: MyScope) {
  if (!scope) return "Not assigned";
  if (scope.allCompanies) return "All companies";
  if (!scope.companies.length) return "Nothing yet";
  return scope.companies.length <= 2
    ? scope.companies.map((company) => company.name).join(", ")
    : plural(scope.companies.length, "company", "companies");
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
  const scope = useResource<MyScope>(open ? "setup/access/me" : null);
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
        <div className="flex flex-col">
          <dt className="text-[13px] text-grey">Can see</dt>
          <dd className="m-0 font-semibold">
            {scope.loading ? (
              <Skeleton className="mt-1 h-5 w-40" />
            ) : scope.error ? (
              <span className="font-normal text-grey">
                Connect to see what you can reach.
              </span>
            ) : (
              <>
                {myScopeLabel(scope.data)}
                {scope.data && !scope.data.allCompanies ? (
                  <CardNote>
                    {plural(scope.data.vehicles.length, "vehicle", "vehicles")}
                  </CardNote>
                ) : null}
              </>
            )}
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

// The signed-in person, and their menu: their access, their preferences and signing out.
function UserMenu({
  session,
  displayName,
  open,
  onToggle,
  onAccess,
  onPreferences,
  onSignOut,
}: {
  session: Session | null;
  displayName: string;
  open: boolean;
  onToggle: () => void;
  onAccess: () => void;
  onPreferences: () => void;
  onSignOut: () => void;
}) {
  const letters = session ? initials(session.firstName, session.lastName) : "";
  return (
    <>
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={onToggle}
        className="prof"
      >
        <span className="av" aria-hidden="true">
          {letters}
        </span>
        <span className="sr-only">{displayName || "Your account"}</span>
      </button>
      {open && (
        <div role="menu" className="pmenu">
          <div className="pwho" role="presentation">
            <span className="av" aria-hidden="true">
              {letters}
            </span>
            <div>
              <b>{displayName || "Your account"}</b>
              <small>{session?.role || "Loading your access"}</small>
            </div>
          </div>
          <div className="flex flex-col gap-0.5 border-t border-divider pt-2">
            <MenuButton onClick={onAccess}>Your access</MenuButton>
            <MenuButton onClick={onPreferences}>Your preferences</MenuButton>
            <MenuButton onClick={onSignOut}>Sign out</MenuButton>
          </div>
        </div>
      )}
    </>
  );
}
