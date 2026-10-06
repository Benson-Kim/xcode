"use client";

import { useState } from "react";

import { plural, type Formatter } from "@xcode/shared/format";
import {
  REVENUE_REPORT_PERIODS,
  revenuePeriodLabel,
  type RevenueReportPeriod,
} from "@xcode/shared/revenue";

import { useAppearance } from "../../lib/appearance";
import { apiRequest, useResource, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import type { ExpenseBucket } from "../../lib/types";
import { recurringFrequency } from "../recurringPresentation";
import { shiftDate } from "../revenueFormat";
import {
  Banner,
  Button,
  Card,
  CardAction,
  CardHeader,
  CardList,
  CardListItem,
  CellNote,
  CurrencyInput,
  DataTable,
  ErrorSummary,
  Field,
  FormActions,
  FormLayout,
  Grid2,
  Hint,
  ListSkeleton,
  Note,
  PageHeader,
  RowButton,
  SegmentedControl,
  SelectInput,
  Spacer,
  Stat,
  StatGrid,
  StatGridSkeleton,
  StatusBadge,
  SubHeading,
  Tabs,
  Td,
  TextInput,
  Toolbar,
  Tr,
  useToast,
} from "../ui";
import { costBucket, expenseBucketNames, type Company, type RecurringItem, type Vehicle, type VehicleReport } from "./shared";
import { VehicleInvestmentTab } from "./VehicleInvestment";

type CompanyChoice = { id: string; name: string; active?: boolean };

export function VehiclesPage({
  onOpenRecurring,
  onAddRecurring,
}: {
  onOpenRecurring?: (itemId: string) => void;
  onAddRecurring?: (vehicleId: string) => void;
}) {
  const { can } = useSession();
  const { appearance } = useAppearance();
  const { formatDateOnly, kes } = useFormats();
  // invest.view alone lists the vehicles read-only, to reach each one's Investment tab.
  const canManage = can("vehicles.manage");
  const vehicles = useStreamedList<Vehicle>("setup/vehicles");
  // Vehicle managers may not manage companies; ask the server for active company options in that case. A read-only
  // list takes its companies from the vehicles themselves.
  const companyList = useStreamedList<Company>(canManage && can("companies.manage") ? "setup/companies" : null);
  const companyOptions = useResource<CompanyChoice[]>(canManage && !can("companies.manage") ? "setup/vehicles/company-options" : null);
  // The organization's business date, never the computer clock; undefined until the appearance has loaded.
  const today = appearance?.businessDate;
  const [filter, setFilter] = useState("all");
  // The vehicle being edited (a null id adds one). After a save it shows the vehicle as saved until the reloaded list
  // arrives, then the server's copy, so what the server works out (active, targets, counts) is never a local guess.
  const [editing, setEditing] = useState<{ id: string | null; saved?: Vehicle; rows?: Vehicle[] } | null>(null);
  const rows = vehicles.items;
  const companies = companyChoices(rows, companyList.items, companyOptions.data);
  const editedVehicle = editing?.id
    ? editing.saved && editing.rows === rows
      ? editing.saved
      : (rows.find((vehicle) => vehicle.id === editing.id) ?? editing.saved)
    : undefined;

  if (editing)
    return (
      <VehicleEditor
        vehicle={editedVehicle}
        // A new vehicle starts on the filtered company only while it can be chosen: never on an archived one.
        defaultCompany={companies.some((company) => company.id === filter && company.active !== false) ? filter : ""}
        companies={companies}
        today={today}
        onOpenRecurring={onOpenRecurring}
        onAddRecurring={onAddRecurring}
        onClose={() => setEditing(null)}
        onSaved={(saved) => {
          vehicles.reload();
          setEditing({ id: saved.id, saved, rows });
        }}
      />
    );

  const visible = rows.filter(
    (vehicle) => filter === "all" || vehicle.companyId === filter,
  );
  return (
    <section>
      <PageHeader
        title="Vehicles"
        description="Registration, company, weekly target, and the scheduled items that post to each vehicle."
      />
      {(vehicles.error || companyOptions.error) && <Banner className="mt-5">{vehicles.error || companyOptions.error}</Banner>}
      <Toolbar>
        <label htmlFor="vehicle-filter" className="text-[13px] text-grey">
          Company
        </label>
        <SelectInput
          id="vehicle-filter"
          density="compact"
          inline
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">All companies</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </SelectInput>
        {!vehicles.loading && (
          <Hint>{plural(visible.length, "vehicle", "vehicles")}</Hint>
        )}
        <Spacer />
        {canManage && <Button tone="ok" onClick={() => setEditing({ id: null })}>Add vehicle</Button>}
      </Toolbar>
      <DataTable
        // Targets and scheduled items are for vehicle managers; the server leaves them out for anyone else.
        columns={[
          { label: "Registration" },
          { label: "Company" },
          { label: "Status" },
          ...(canManage ? [{ label: "Weekly target", numeric: true }] : []),
          { label: "In the fleet from" },
          ...(canManage ? [{ label: "Scheduled items", numeric: true }] : []),
        ]}
        loading={vehicles.loading}
        pendingRows={filter === "all" ? vehicles.pendingRows : 0}
        loadingLabel="Loading vehicles"
        isEmpty={!visible.length}
        failed={Boolean(vehicles.error)}
        emptyMessage={filter === "all" ? "No vehicles yet. Add the first one above." : "No vehicles in this company yet."}
      >
        {visible.map((vehicle) => {
          const status = fleetStatus(vehicle, formatDateOnly);
          return (
            <Tr key={vehicle.id}>
              <Td label="Registration">
                <RowButton onClick={() => setEditing({ id: vehicle.id })}>{vehicle.registration}</RowButton>
              </Td>
              <Td label="Company">{vehicle.companyName}</Td>
              <Td label="Status">
                <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
              </Td>
              {canManage && (
                <Td label="Weekly target" numeric>
                  {/* Leaving the fleet ends the target: no "KES 0 a day" for a vehicle that no longer runs. */}
                  {status.left ? (
                    <>
                      —<CellNote>Target ended</CellNote>
                    </>
                  ) : (
                    <>
                      {kes(vehicle.weeklyTarget ?? 0)}
                      <CellNote>About {kes(Math.round((vehicle.weeklyTarget ?? 0) / 7))} a day</CellNote>
                    </>
                  )}
                </Td>
              )}
              <Td label="In the fleet from">{formatDateOnly(vehicle.joinedOn)}</Td>
              {canManage && (
                <Td label="Scheduled items" numeric>
                  {vehicle.recurringItems ?? 0}
                </Td>
              )}
            </Tr>
          );
        })}
      </DataTable>
    </section>
  );
}

// A leave date means the vehicle is retired: it has left once it is no longer active, and until then it leaves on
// that date. Without one, a vehicle that is not active has not joined yet: the business date is before its join date.
function fleetStatus(
  vehicle: Vehicle,
  formatDateOnly: Formatter["formatDateOnly"],
): { label: string; tone: "ok" | "warn" | "off" | "neutral"; left: boolean } {
  if (vehicle.leftOn)
    return vehicle.active === false
      ? { label: `Left fleet ${formatDateOnly(vehicle.leftOn)}`, tone: "off", left: true }
      : { label: `Leaves the fleet ${formatDateOnly(vehicle.leftOn)}`, tone: "warn", left: false };
  return vehicle.active === false
    ? { label: `Joins ${formatDateOnly(vehicle.joinedOn)}`, tone: "neutral", left: false }
    : { label: "Active", tone: "ok", left: false };
}

function companyChoices(vehicles: Vehicle[], companies?: Company[], options?: CompanyChoice[]): CompanyChoice[] {
  const byId = new Map<string, CompanyChoice>();
  for (const company of companies ?? []) byId.set(company.id, { id: company.id, name: company.name, active: company.active });
  for (const company of options ?? []) byId.set(company.id, company);
  // A company known only through its vehicles is one the server did not offer (archived, or not loaded yet): it
  // filters the list but is never offered for a vehicle to join.
  for (const vehicle of vehicles) {
    if (!byId.has(vehicle.companyId))
      byId.set(vehicle.companyId, { id: vehicle.companyId, name: vehicle.companyName, active: false });
  }
  return [...byId.values()].sort((left, right) => left.name.localeCompare(right.name));
}

const REGISTRATION = /^K[A-Z]{2}[0-9]{3}[A-Z]$/;

function normaliseRegistration(value: string) {
  const compact = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return REGISTRATION.test(compact)
    ? `${compact.slice(0, 3)} ${compact.slice(3)}`
    : null;
}

// Saving, retiring and restoring carry no typed reason: the server writes one for the change log.
type Errors = Partial<Record<"registration" | "companyId" | "weeklyTarget" | "joinedOn", string>>;

type VehicleTab = "details" | "report" | "scheduled" | "investment";

function VehicleEditor({
  vehicle,
  defaultCompany,
  companies,
  today,
  onOpenRecurring,
  onAddRecurring,
  onClose,
  onSaved,
}: {
  vehicle?: Vehicle;
  defaultCompany: string;
  companies: CompanyChoice[];
  today?: string;
  onOpenRecurring?: (itemId: string) => void;
  onAddRecurring?: (vehicleId: string) => void;
  onClose: () => void;
  onSaved: (vehicle: Vehicle) => void;
}) {
  const toast = useToast();
  const { can } = useSession();
  const { formatDateOnly, formatDateRange, kes } = useFormats();
  const isNew = !vehicle;
  // A null date has not been chosen yet and follows the business date, which may still be loading.
  const [form, setForm] = useState<{ registration: string; companyId: string; weeklyTarget: string; joinedOn: string | null }>({
    registration: vehicle?.registration ?? "",
    companyId: vehicle?.companyId ?? defaultCompany,
    weeklyTarget: vehicle?.weeklyTarget != null ? String(vehicle.weeklyTarget) : "",
    joinedOn: vehicle?.joinedOn ?? null,
  });
  const joinedOn = form.joinedOn ?? today ?? "";
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [lifecycleInput, setLifecycleDate] = useState<string | null>(vehicle?.leftOn ?? null);
  const lifecycleDate = lifecycleInput ?? today ?? "";
  const [returnInput, setReturnDate] = useState<string | null>(null);
  const returnedOn = returnInput ?? today ?? "";
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<VehicleTab>("details");
  // Each tab needs its own permission: the details and the report need vehicles.manage.
  const tabs: { value: VehicleTab; label: string }[] = [
    ...(can("vehicles.manage")
      ? [
          { value: "details" as const, label: "Details" },
          { value: "report" as const, label: "Report" },
        ]
      : []),
    ...(can("commitments.view") ? [{ value: "scheduled" as const, label: "Scheduled items" }] : []),
    ...(can("invest.view") ? [{ value: "investment" as const, label: "Investment" }] : []),
  ];
  const shownTab = tabs.some((option) => option.value === tab) ? tab : (tabs[0]?.value ?? "details");
  const weekly = Number(form.weeklyTarget) || 0;
  const companyName = companies.find((company) => company.id === form.companyId)?.name ?? vehicle?.companyName;
  // Retired means it has a leave date; a vehicle that is not active without one joins after the business date.
  const retired = Boolean(vehicle?.leftOn);
  const joinsLater = Boolean(vehicle && !vehicle.leftOn && vehicle.active === false);
  // Newest first: the stretch someone is most likely to be checking is the one that just ended.
  const away = [...(vehicle?.away ?? [])].reverse();

  async function retireVehicle() {
    if (!vehicle || retired) return;
    if (!lifecycleDate) return setSaveError("Choose the date it leaves the fleet.");
    setBusy(true);
    setSaveError("");
    try {
      await apiRequest(`setup/vehicles/${vehicle.id}/retire`, {
        method: "POST",
        body: JSON.stringify({ leftOn: lifecycleDate }),
      });
      toast(`${vehicle.registration} left the fleet.`);
      onSaved({ ...vehicle, leftOn: lifecycleDate, active: false });
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function restoreVehicle() {
    if (!vehicle || !retired) return;
    if (!returnedOn) return setSaveError("Choose the date it returns to the fleet.");
    setBusy(true);
    setSaveError("");
    try {
      await apiRequest(`setup/vehicles/${vehicle.id}/restore`, {
        method: "POST",
        body: JSON.stringify({ returnedOn }),
      });
      toast(`${vehicle.registration} returned to the active fleet.`);
      // A leave undone on its own date took effect for no day, so it leaves no stretch away behind (D4).
      const away =
        vehicle.leftOn && returnedOn > vehicle.leftOn
          ? [...(vehicle.away ?? []), { leftOn: vehicle.leftOn, returnedOn }]
          : vehicle.away;
      onSaved({ ...vehicle, leftOn: null, active: true, away });
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const registration = isNew
      ? normaliseRegistration(form.registration)
      : vehicle.registration;
    const next: Errors = {};
    if (isNew && !form.registration.trim())
      next.registration = "Enter the registration number.";
    else if (!registration)
      next.registration = "Use the Kenyan format, for example KDA 482M.";
    if (!form.companyId) next.companyId = "Choose the PSV company.";
    if (weekly <= 0) next.weeklyTarget = "Enter the weekly target in KES.";
    if (!joinedOn) next.joinedOn = "Enter the date it joined the fleet.";
    else if (today && joinedOn > today) next.joinedOn = "The join date cannot be after the business date.";
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length || !registration) return;
    if (retired) {
      setSaveError("Restore this vehicle before editing its details.");
      return;
    }
    if (!isNew && vehicle.companyId === form.companyId && vehicle.weeklyTarget === weekly && vehicle.joinedOn === joinedOn) {
      toast("No changes to save.");
      return;
    }
    setBusy(true);
    try {
      const result = await apiRequest<{ id: string }>(isNew ? "setup/vehicles" : `setup/vehicles/${vehicle.id}`, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify({
          registration,
          companyId: form.companyId,
          weeklyTarget: weekly,
          joinedOn,
        }),
      });
      toast(isNew ? `${registration} added.` : `Changes saved for ${registration}.`);
      onSaved({
        ...(vehicle ?? { targets: [], recurringItems: 0 }),
        id: result.id,
        registration,
        companyId: form.companyId,
        companyName: companyName ?? "",
        weeklyTarget: weekly,
        joinedOn,
      });
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const history = [...(vehicle?.targets ?? [])].sort((left, right) => right.effectiveFrom.localeCompare(left.effectiveFrom) || right.revision - left.revision);
  const back = (
    <FormActions>
      <Button tone="quiet" onClick={onClose}>
        Back
      </Button>
    </FormActions>
  );
  const details = (
      <FormLayout>
        <ErrorSummary count={Object.keys(errors).length} />
        {saveError && <Banner>{saveError}</Banner>}
        {joinsLater && (
          <Note tone="info">
            Joins the fleet on {formatDateOnly(vehicle!.joinedOn)}, after the business date.
            {today ? ` To save a change, set a join date on or before ${formatDateOnly(today)}.` : ""}
          </Note>
        )}
        <Card density="form">
          <CardHeader title="Vehicle" />
          <Grid2>
            <Field
              id="vehicle-registration"
              label="Registration number"
              error={errors.registration}
              hint={
                isNew
                  ? "Kenyan format, for example KDA 482M."
                  : "A registration cannot change. Add the vehicle again if it is re-registered."
              }
            >
              <TextInput
                value={form.registration}
                disabled={!isNew || retired}
                placeholder="KDA 482M"
                autoCapitalize="characters"
                onChange={(event) =>
                  setForm({
                    ...form,
                    registration: event.target.value.toUpperCase(),
                  })
                }
              />
            </Field>
            <Field id="vehicle-company" label="PSV company" error={errors.companyId}>
              <SelectInput value={form.companyId} disabled={retired} onChange={(event) => setForm({ ...form, companyId: event.target.value })}>
                <option value="">Choose a company</option>
                {companies
                  .filter((company) => company.active !== false || company.id === vehicle?.companyId)
                  .map((company) => (
                    <option key={company.id} value={company.id}>
                      {company.name}{company.active === false ? " (archived)" : ""}
                    </option>
                  ))}
              </SelectInput>
            </Field>
            <Field
              id="vehicle-target"
              label="Weekly performance target"
              error={errors.weeklyTarget}
              hint={`${weekly ? `About ${kes(Math.round(weekly / 7))} a day.` : "Revenue you expect in a Monday to Sunday week."}${isNew ? "" : " A change applies from today. Past days keep their old target."}`}
            >
              <CurrencyInput disabled={retired} min="1" step="1" value={form.weeklyTarget} onChange={(event) => setForm({ ...form, weeklyTarget: event.target.value })} />
            </Field>
            <Field id="vehicle-joined" label="In the fleet from" error={errors.joinedOn} hint="Missing revenue days are only counted from this date.">
              <TextInput disabled={retired} type="date" max={today} value={joinedOn} onChange={(event) => setForm({ ...form, joinedOn: event.target.value })} />
            </Field>
          </Grid2>
          {history.length > 1 && (
            <div>
              <p className="m-0 text-sm font-semibold">Target history</p>
              <CardList>
                {history.map((target, index) => (
                  <CardListItem
                    key={`${target.effectiveFrom}-${target.revision}`}
                    left={`${kes(target.weeklyAmount)} a week`}
                    rightSub={`${index === 0 ? "From" : "Was from"} ${formatDateOnly(target.effectiveFrom)}`}
                  />
                ))}
              </CardList>
            </div>
          )}
        </Card>
        {vehicle && (
          <Card density="form">
            <CardHeader
              title="Fleet lifecycle"
              description="Leaving the fleet stops targets, scheduled item shares, and future report postings from that date."
            />
            {retired ? (
              <>
                <Hint>
                  {vehicle.active === false ? "Left the fleet on" : "Leaves the fleet on"} {formatDateOnly(vehicle.leftOn!)}.
                </Hint>
                <Grid2 narrow>
                  <Field
                    id="vehicle-returned-on"
                    label="Returns to the fleet"
                    hint={
                      returnedOn > vehicle.leftOn!
                        ? `${formatDateRange(vehicle.leftOn!, shiftDate(returnedOn, -1))} is recorded as time away: those days are neither expected nor missing.`
                        : "Returning on the day it left undoes the leave outright."
                    }
                  >
                    <TextInput
                      type="date"
                      min={vehicle.leftOn!}
                      max={today}
                      value={returnedOn}
                      onChange={(event) => setReturnDate(event.target.value)}
                    />
                  </Field>
                </Grid2>
                <FormActions>
                  <Button
                    tone="ok"
                    disabled={busy}
                    onClick={() => void restoreVehicle()}
                  >
                    Restore to active fleet
                  </Button>
                </FormActions>
              </>
            ) : joinsLater ? (
              <Hint>It can leave the fleet once it has joined.</Hint>
            ) : (
              <>
                <Grid2 narrow>
                  <Field id="vehicle-left-on" label="Leaves the fleet" hint="No target or scheduled posting is active on this date.">
                    <TextInput type="date" min={vehicle.joinedOn} max={today} value={lifecycleDate} onChange={(event) => setLifecycleDate(event.target.value)} />
                  </Field>
                </Grid2>
                <FormActions>
                  <Button
                    tone="warn"
                    disabled={busy}
                    onClick={() => void retireVehicle()}
                  >
                    Retire vehicle
                  </Button>
                </FormActions>
              </>
            )}
            {away.length > 0 && (
              <div>
                <p className="m-0 text-sm font-semibold">Time away from the fleet</p>
                <CardList>
                  {away.map((period) => (
                    <CardListItem
                      key={period.leftOn}
                      left={formatDateRange(period.leftOn, shiftDate(period.returnedOn, -1))}
                      rightSub={`Back on ${formatDateOnly(period.returnedOn)}`}
                    />
                  ))}
                </CardList>
              </div>
            )}
          </Card>
        )}
        <FormActions>
          <Button tone="ok" disabled={busy || retired} onClick={() => void save()}>
            {isNew ? "Add vehicle" : "Save changes"}
          </Button>
          <Button tone="quiet" onClick={onClose}>
            Cancel
          </Button>
        </FormActions>
      </FormLayout>
  );
  return (
    <section>
      <PageHeader
        title={isNew ? "Add vehicle" : vehicle.registration}
        description={
          isNew
            ? "It shows on reports and the dashboard straight away."
            : `${companyName}${retired ? " · Left the fleet" : joinsLater ? ` · Joins ${formatDateOnly(vehicle.joinedOn)}` : ""}`
        }
      />
      {isNew ? (
        details
      ) : (
        <Tabs id="vehicle" label={`About ${vehicle.registration}`} options={tabs} value={shownTab} onChange={setTab}>
          {shownTab === "details" && details}
          {shownTab === "report" && (
            <FormLayout>
              <VehicleReportCard vehicle={vehicle} />
              {back}
            </FormLayout>
          )}
          {shownTab === "scheduled" && (
            <FormLayout>
              <VehicleRecurringCard vehicle={vehicle} onOpen={onOpenRecurring} onAdd={onAddRecurring} />
              {back}
            </FormLayout>
          )}
          {shownTab === "investment" && (
            <>
              <VehicleInvestmentTab vehicle={vehicle} today={today} />
              <div className="mt-4">{back}</div>
            </>
          )}
        </Tabs>
      )}
    </section>
  );
}

// The vehicle report (contract C6), with the design's figures in the design's order. Postings are listed per item,
// each under its bucket or as savings. A revision that renamed the item or moved it to another bucket gets its own
// line, so no posting shows under a bucket it was not counted in.
function VehicleReportCard({ vehicle }: { vehicle: Vehicle }) {
  const { formatDateOnly, formatDateRange, kes, money } = useFormats();
  const [period, setPeriod] = useState<RevenueReportPeriod>("month");
  const report = useResource<VehicleReport>(`setup/vehicles/${vehicle.id}/report?period=${period}`);
  const data = report.data;
  const grouped = [...(data?.postings ?? []).reduce((items, posting) => {
    const bucket = costBucket(posting);
    const key = JSON.stringify([posting.itemId, posting.name, posting.kind, bucket]);
    const item = items.get(key) ?? { id: key, name: posting.name, kind: posting.kind, bucket, total: 0, dates: [] as string[] };
    item.total += posting.amount;
    item.dates.push(posting.date);
    return items.set(key, item);
  }, new Map<string, { id: string; name: string; kind: number; bucket: ExpenseBucket | null; total: number; dates: string[] }>()).values()];
  return (
    <Card>
      <CardHeader
        title={`${revenuePeriodLabel(period)}${data ? `, ${formatDateRange(data.from, data.through)}` : ""}`}
        description="Money in and money out, counted on the day it moved. Fuel and crew pay are not tracked; revenue is recorded net of them."
      />
      <SegmentedControl
        label="Report period"
        options={REVENUE_REPORT_PERIODS.map((option) => ({ ...option }))}
        value={period}
        onChange={setPeriod}
        className="self-start"
      />
      {report.error ? (
        <Hint>{report.error}</Hint>
      ) : report.loading || !data ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-2.5">
          <span className="sr-only">Loading the vehicle report</span>
          <StatGridSkeleton count={9} />
          <ListSkeleton rows={2} />
        </div>
      ) : (
        <>
          <StatGrid>
            <Stat label="Money in" value={kes(data.moneyIn)} />
            <Stat label="Target" value={kes(data.target)} />
            <Stat label="Repairs and maintenance" value={kes(data.repairs)} />
            <Stat label="Recurring charges" value={kes(data.charges)} />
            <Stat label="Loan repayments" value={kes(data.loans)} />
            <Stat label="Money out" value={kes(data.moneyOut)} />
            <Stat label="Net contribution" value={money(data.net)} tone={data.net < 0 ? "bad" : undefined} />
            <Stat label="Savings set aside" value={kes(data.savings)} />
            <Stat label="After savings" value={money(data.afterSavings)} tone={data.afterSavings < 0 ? "bad" : undefined} />
          </StatGrid>
          <SubHeading>Postings in this period</SubHeading>
          {grouped.length ? (
            <CardList>
              {grouped.map((item) => (
                <CardListItem
                  key={item.id}
                  left={item.name}
                  leftSub={`${item.bucket ? expenseBucketNames[item.bucket] : "Savings"}. ${
                    item.dates.length <= 3
                      ? item.dates.map(formatDateOnly).join(", ")
                      : `${item.dates.length} postings, ${formatDateOnly(item.dates[0])} to ${formatDateOnly(item.dates[item.dates.length - 1])}`
                  }`}
                  right={kes(item.total)}
                />
              ))}
            </CardList>
          ) : (
            <Hint>Nothing posted in this period.</Hint>
          )}
        </>
      )}
    </Card>
  );
}

function VehicleRecurringCard({
  vehicle,
  onOpen,
  onAdd,
}: {
  vehicle: Vehicle;
  onOpen?: (itemId: string) => void;
  onAdd?: (vehicleId: string) => void;
}) {
  const { can } = useSession();
  const { appearance } = useAppearance();
  const { formatDateOnly, kes } = useFormats();
  const recurring = useStreamedList<RecurringItem>(can("commitments.view") ? "setup/recurring" : null);
  if (!can("commitments.view")) return null;
  const today = appearance?.businessDate;
  const items = recurring.items.filter((item) => item.allocations.some((allocation) => allocation.vehicleId === vehicle.id));
  return (
    <Card>
      <CardHeader title={`Scheduled items for ${vehicle.registration}`} description="This vehicle's share of each scheduled expense or saving" />
      {recurring.loading ? (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading scheduled items</span>
          <ListSkeleton rows={2} />
        </div>
      ) : recurring.error ? (
        <Hint>{recurring.error}</Hint>
      ) : items.length ? (
        <CardList>
          {items.map((item) => {
            const allocation = item.allocations.find((candidate) => candidate.vehicleId === vehicle.id)!;
            const share = allocation.amount;
            const stopped = allocation.active === false || Boolean(item.stoppedFrom) || Boolean(today && item.end && item.end < today);
            return (
              <CardListItem
                key={item.id}
                left={onOpen ? <RowButton onClick={() => onOpen(item.id)}>{item.name}</RowButton> : item.name}
                leftSub={`${item.note ? `${item.note}. ` : ""}${recurringFrequency(item)}${
                  !stopped
                    ? ""
                    : allocation.active !== false
                      ? ". Stopped"
                      : vehicle.leftOn
                        ? ". Left the fleet"
                        : `. Posts once it joins on ${formatDateOnly(vehicle.joinedOn)}`
                }`}
                right={kes(share)}
                rightSub={item.allocations.length > 1 ? `of ${kes(item.activeAmount ?? item.amount)}` : "each time"}
              />
            );
          })}
        </CardList>
      ) : (
        <Hint>Nothing scheduled for this vehicle yet.</Hint>
      )}
      {vehicle.active !== false && can("commitments.manage") && onAdd && (
        <CardAction onClick={() => onAdd(vehicle.id)}>Add scheduled item for {vehicle.registration}</CardAction>
      )}
    </Card>
  );
}
