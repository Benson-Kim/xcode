"use client";

import { useEffect, useState } from "react";

import type { Period } from "@xcode/shared/periods";
import {
  pettyCashEntriesPath,
  pettyCashOverviewPath,
  type PettyCashEntryPage,
  type PettyCashKind,
  type PettyCashOverview,
  type PettyCashPermissions,
  type PettyCashStatus,
} from "@xcode/shared/pettyCash";

import { useAppearance } from "../../lib/appearance";
import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import { PeriodPicker } from "../period/PeriodPicker";
import { useReportExport } from "../reports/exportReport";
import { BandSkeleton } from "../revenue/RegPlate";
import {
  Banner,
  Button,
  HeroBand,
  PageHeader,
  Pager,
  RetryBanner,
  usePaging,
  useToast,
} from "../ui";
import { ApproveButton, PettyCashExport } from "./BarActions";
import { CashTable } from "./CashTable";
import { EntriesTable, selectable } from "./EntriesTable";
import { EntryDialog, type EntryDialogState } from "./EntryDialog";
import { FigureCards } from "./FigureCards";
import { FiltersBar, type StatusFilter } from "./FiltersBar";
import { ReasonDialog, type ReasonState } from "./ReasonDialogs";
import type { EntryActions } from "./RowActions";
import { BULK, useApprovals } from "./useApprovals";
import { useSelection } from "./useSelection";
import { ViewPills } from "./ViewPills";

type Tab = "expenses" | "cash";

const TABS: { value: Tab; label: string }[] = [
  { value: "expenses", label: "Expenses" },
  { value: "cash", label: "Cash received" },
];

const KINDS: Record<Tab, PettyCashKind | PettyCashKind[]> = {
  expenses: "expense",
  cash: ["cash", "credit"],
};

export function PettyCashPage({
  initialStatus,
  initialDate,
}: {
  initialStatus?: PettyCashStatus;
  initialDate?: string;
}) {
  const formats = useFormats();
  const toast = useToast();
  const appearanceDate = useAppearance().appearance?.businessDate;
  const [tab, setTab] = useState<Tab>("expenses");
  const [chosen, setChosen] = useState<Period | null>(
    initialDate ? { from: initialDate, to: initialDate, unit: "day" } : null,
  );
  const [holderId, setHolderId] = useState("");
  const [status, setStatus] = useState<StatusFilter>(initialStatus ?? "all");
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [entryDialog, setEntryDialog] = useState<EntryDialogState | null>(null);
  const [reasoning, setReasoning] = useState<ReasonState | null>(null);
  const { can } = useSession();
  const exporter = useReportExport();

  useEffect(() => {
    const timer = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(timer);
  }, [search]);

  // Without a period the server answers for the business date, which is how the page learns it. What the person may
  // do and who holds a float do not depend on the days or the filter, so the last answer keeps them while the next
  // loads.
  const overview = useResource<PettyCashOverview>(
    pettyCashOverviewPath({
      from: chosen?.from,
      to: chosen?.to,
      holderId: holderId || undefined,
    }),
  );
  const [known, setKnown] = useState<PettyCashOverview | undefined>(
    overview.data,
  );
  if (overview.data && overview.data !== known) setKnown(overview.data);

  const permissions = known?.permissions;
  const businessDate = known?.businessDate ?? appearanceDate ?? null;
  const range = chosen ?? (known ? { from: known.from, to: known.to } : null);
  const period: Period | null = range && {
    ...range,
    unit: chosen?.unit ?? "day",
  };
  const oneDay = range ? range.from === range.to : true;
  // A new entry opens on today when what is shown contains it, otherwise on its last day.
  const formDate =
    businessDate &&
    range &&
    !(range.from <= businessDate && businessDate <= range.to)
      ? range.to
      : businessDate;

  const paging = usePaging(
    `${range?.from}|${range?.to}|${holderId}|${query}|${tab}|${status}`,
  );
  const list = useResource<PettyCashEntryPage>(
    range
      ? pettyCashEntriesPath({
          from: range.from,
          to: range.to,
          holderId: holderId || undefined,
          q: query || undefined,
          page: paging.page,
          pageSize: paging.pageSize,
          kind: KINDS[tab],
          ...(tab === "expenses" && status !== "all"
            ? { status: status as PettyCashStatus }
            : {}),
        })
      : null,
  );
  if (list.data) paging.stepBack(list.data.total);
  const otherTab: Tab = tab === "expenses" ? "cash" : "expenses";
  const other = useCount(range, holderId, query, KINDS[otherTab]);
  const selection = useSelection(
    `${range?.from}|${range?.to}|${holderId}|${query}|${tab}|${status}|${paging.page}|${paging.pageSize}`,
  );
  const items = list.data?.items ?? [];
  const loading = range === null ? !overview.error : list.loading;

  function refresh() {
    overview.reload();
    list.reload();
    other.reload();
  }

  // A refusal keeps the explanation on the page; a save says so in a toast. Either closes the dialogs and reloads.
  function finish(message: string, toasted?: string) {
    setNotice(message);
    setEntryDialog(null);
    setReasoning(null);
    if (toasted) toast(toasted);
    refresh();
  }
  const conflict = (message: string) => finish(message);
  const saved = (message: string) => finish("", message);

  const { busyId, approve, approveMany } = useApprovals({
    refresh,
    onNotice: setNotice,
    onBulkDone: selection.clear,
  });

  const ticked = items.filter(
    (entry) => selectable(entry) && selection.ids.includes(entry.id),
  );
  const canTick = Boolean(permissions?.canApproveItem);
  const waiting = overview.data?.figures;

  const actions: EntryActions = {
    busyId,
    onApprove: (entry) => void approve(entry),
    onSendBack: (entry) => setReasoning({ action: "sendBack", entry }),
    onReject: (entry) => setReasoning({ action: "reject", entry }),
    onReopen: (entry) => setReasoning({ action: "reopen", entry }),
    onEdit: (entry) => setEntryDialog({ kind: entry.kind, entry }),
    onRemove: (entry) => setReasoning({ action: "remove", entry }),
  };

  const holderName = holderId
    ? known?.holders.find((holder) => holder.id === holderId)?.name
    : undefined;

  return (
    <>
      <PageHeader title="Petty cash" description="" srOnlyTitle />

      <HeroBand
        variant="eq"
        label="Cash balance equals opening balance plus cash issued minus expenses minus credit notes"
        period={
          period && businessDate ? (
            <PeriodPicker
              period={period}
              businessDate={businessDate}
              firstDayOfWeek={formats.firstDayOfWeek()}
              onChange={setChosen}
            />
          ) : (
            <BandSkeleton />
          )
        }
        trailing={
          <>
            {permissions && (
              <RecordButtons
                tab={tab}
                permissions={permissions}
                onRecord={(kind) => setEntryDialog({ kind })}
              />
            )}
          </>
        }
      >
        <FigureCards
          overview={overview.data}
          label={holderName ? `Cash balance, ${holderName}` : "Cash balance"}
        />
      </HeroBand>

      {notice && <Banner>{notice}</Banner>}

      {overview.error && !known && (
        <RetryBanner onRetry={overview.reload}>{overview.error}</RetryBanner>
      )}

      <FiltersBar
        views={
          <ViewPills
            id="petty"
            label="Petty cash"
            panelId="pcT"
            options={TABS}
            value={tab}
            onChange={setTab}
            counts={{
              [tab]: list.data?.total,
              [otherTab]: other.data?.total,
            }}
          />
        }
        holders={permissions?.canViewAll ? known?.holders : undefined}
        holderId={holderId}
        onHolderChange={setHolderId}
        status={tab === "expenses" ? status : undefined}
        onStatusChange={setStatus}
        search={search}
        onSearchChange={setSearch}
        actions={
          range && (
            <>
              {can("reports.export") && (
                <PettyCashExport
                  exporter={exporter}
                  tab={tab}
                  range={range}
                  holderId={holderId}
                  status={status}
                  query={query}
                />
              )}
              {tab === "expenses" && (
                <ApproveButton
                  ticked={canTick ? ticked : []}
                  canApproveDay={Boolean(permissions?.canApproveDay)}
                  range={range}
                  holderId={holderId}
                  figures={waiting}
                  busy={busyId === BULK}
                  onApprove={(path, body, nothing) =>
                    void approveMany(path, body, nothing)
                  }
                />
              )}
            </>
          )
        }
      />
      {exporter.error && <Banner>{exporter.error}</Banner>}

      {list.error && <Banner>{list.error}</Banner>}

      <div
        role="tabpanel"
        id="pcT"
        aria-labelledby={`petty-tab-${tab}`}
        className="stack"
      >
        {tab === "expenses" ? (
          <EntriesTable
            entries={items}
            total={list.data?.total ?? 0}
            days={!oneDay}
            loading={loading}
            failed={Boolean(list.error)}
            actions={actions}
            selection={
              canTick
                ? {
                    ids: selection.ids,
                    onToggle: (e) => selection.toggle(e.id),
                  }
                : undefined
            }
          />
        ) : (
          <CashTable
            entries={items}
            total={list.data?.total ?? 0}
            days={!oneDay}
            searching={Boolean(query)}
            loading={loading}
            failed={Boolean(list.error)}
            canDelete={Boolean(permissions?.canDeleteCash)}
            onRemove={actions.onRemove}
          />
        )}
      </div>

      <Pager
        page={paging.page}
        pageSize={paging.pageSize}
        total={list.data?.total ?? 0}
        onPageChange={paging.setPage}
        onPageSizeChange={paging.setPageSize}
      />

      {permissions && formDate && businessDate && (
        <EntryDialog
          state={entryDialog}
          date={formDate}
          businessDate={businessDate}
          permissions={permissions}
          holderId={holderId}
          holders={known?.holders}
          floats={known?.floats}
          onSaved={saved}
          onConflict={conflict}
          onClose={() => setEntryDialog(null)}
        />
      )}

      <ReasonDialog
        state={reasoning}
        onDone={saved}
        onConflict={conflict}
        onClose={() => setReasoning(null)}
      />
    </>
  );
}

// What this person may record in the view shown: the actions on the headline card. Spending needs a float of their own
// or the right to add for another manager.
function RecordButtons({
  tab,
  permissions,
  onRecord,
}: {
  tab: Tab;
  permissions: PettyCashPermissions;
  onRecord: (kind: PettyCashKind) => void;
}) {
  if (tab === "expenses")
    return permissions.canSpend &&
      (permissions.holderId || permissions.canSpendOther) ? (
      <Button tone="primary" onClick={() => onRecord("expense")}>
        Record spending
      </Button>
    ) : null;
  return (
    <>
      {permissions.canCredit && (
        <Button tone="outline" onClick={() => onRecord("credit")}>
          Credit note
        </Button>
      )}
      {permissions.canIssue && (
        <Button tone="primary" onClick={() => onRecord("cash")}>
          Issue cash
        </Button>
      )}
    </>
  );
}

// How many entries of the other tab match the same days, manager and search, for its pill.
function useCount(
  range: { from: string; to: string } | null,
  holderId: string,
  query: string,
  kind: PettyCashKind | PettyCashKind[],
) {
  return useResource<PettyCashEntryPage>(
    range
      ? pettyCashEntriesPath({
          from: range.from,
          to: range.to,
          holderId: holderId || undefined,
          q: query || undefined,
          page: 1,
          pageSize: 1,
          kind,
        })
      : null,
  );
}
