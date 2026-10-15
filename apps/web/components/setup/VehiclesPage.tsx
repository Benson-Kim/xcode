"use client";

import { useState } from "react";

import { MONTH_NAMES } from "@xcode/shared/dates";
import { plural, type Formatter } from "@xcode/shared/format";
import {
  REVENUE_REPORT_PERIODS,
  revenuePeriodLabel,
  vehicleLabel,
  type RevenueReportPeriod,
} from "@xcode/shared/revenue";

import { useAppearance } from "../../lib/appearance";
import {
  apiRequest,
  streamError,
  useResource,
  useStreamedList,
} from "../../lib/data";
import { vehiclesApi } from "../../lib/endpoints/vehicles";
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
  CurrencyInput,
  DataTable,
  Dialog,
  ErrorText,
  Field,
  FieldPair,
  FormActions,
  Grid2,
  Hint,
  ListSkeleton,
  Note,
  PageHeader,
  ListPager,
  RowAction,
  RowButton,
  SegmentedControl,
  SelectInput,
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
import { usePagedList } from "../usePagedList";
import {
  DayTargetGrid,
  EMPTY_TARGETS,
  hasEveryTarget,
  targetFigures,
} from "./DayTargets";
import {
  costBucket,
  expenseBucketNames,
  RegPlate,
  type Company,
  type RecurringItem,
  type Vehicle,
  type VehicleReport,
} from "./shared";
import { TargetsDialog } from "./TargetsDialog";
import { VehicleInvestmentTab } from "./VehicleInvestment";

type CompanyChoice = { id: string; name: string; active?: boolean };

// The released vehicles.manage key stands for adding, editing and setting targets together.
function useVehicleRights() {
  const { can } = useSession();
  const manage = can("vehicles.manage");
  return {
    view: manage || can("vehicles.view"),
    add: manage || can("vehicles.add"),
    edit: manage || can("vehicles.edit"),
    target: manage || can("vehicles.target"),
  };
}

export function VehiclesPage({
  onOpenRecurring,
  onAddRecurring,
}: {
  onOpenRecurring?: (itemId: string) => void;
  onAddRecurring?: (vehicleId: string) => void;
}) {
  const { can } = useSession();
  const { appearance } = useAppearance();
  const { formatDateOnly, formatNumber } = useFormats();
  // invest.view alone lists the vehicles read-only, to reach each one's Investment tab.
  const rights = useVehicleRights();
  const canChange = rights.add || rights.edit;
  const canSeeCompanies = can("companies.manage") || can("companies.view");
  // Vehicle managers may not see companies; ask the server for active company options in that case. A read-only
  // list takes its companies from the vehicles themselves.
  const companyList = useStreamedList<Company>(
    canChange && canSeeCompanies ? "setup/companies" : null,
  );
  const companyOptions = useResource<CompanyChoice[]>(
    canChange && !canSeeCompanies ? "setup/vehicles/company-options" : null,
  );
  // The organization's business date, never the computer clock; undefined until the appearance has loaded.
  const today = appearance?.businessDate;
  const [filter, setFilter] = useState("all");
  // Vehicles come a server page at a time, filtered to the chosen company by the server.
  const vehicles = usePagedList<Vehicle>(
    filter === "all"
      ? "setup/vehicles"
      : `setup/vehicles?companyId=${encodeURIComponent(filter)}`,
  );
  // The vehicle being edited (a null id adds one). After a save it shows the vehicle as saved until the reloaded list
  // arrives, then the server's copy, so what the server works out (active, targets, counts) is never a local guess.
  const [editing, setEditing] = useState<{
    id: string | null;
    saved?: Vehicle;
    rows?: Vehicle[];
  } | null>(null);
  const [targeting, setTargeting] = useState<string | null>(null);
  const rows = vehicles.items;
  const targetedVehicle = targeting
    ? rows.find((vehicle) => vehicle.id === targeting)
    : undefined;
  const scheduledLabel = today
    ? `Scheduled, ${MONTH_NAMES[Number(today.slice(5, 7)) - 1]} ${today.slice(0, 4)}`
    : "Scheduled";
  const companies = companyChoices(
    useCompaniesSeen(rows),
    companyList.items,
    companyOptions.data,
  );
  const editedVehicle = editing?.id
    ? editing.saved && editing.rows === rows
      ? editing.saved
      : (rows.find((vehicle) => vehicle.id === editing.id) ?? editing.saved)
    : undefined;

  return (
    <>
      <PageHeader
        title="Vehicles"
        actions={
          rights.add && !editing ? (
            <Button tone="primary" onClick={() => setEditing({ id: null })}>
              New vehicle
            </Button>
          ) : undefined
        }
      />
      {(vehicles.error || companyOptions.error) && (
        <Banner>{streamError(vehicles) || companyOptions.error}</Banner>
      )}
      <Toolbar>
        <CompanyFilter
          value={filter}
          companies={companies}
          onChange={setFilter}
        />
      </Toolbar>
      <DataTable
        // Targets and scheduled items are for those who view vehicles; the server leaves them out for anyone else.
        columns={[
          { label: "Registration" },
          { label: "Fleet number" },
          { label: "PSV company" },
          ...(rights.view ? [{ label: "Weekly target", numeric: true }] : []),
          { label: "Initial investment", numeric: true },
          ...(rights.view ? [{ label: scheduledLabel, numeric: true }] : []),
          { label: "Actions", numeric: true },
        ]}
        loading={vehicles.loading}
        pendingRows={vehicles.pendingRows}
        loadingLabel="Loading vehicles"
        footer={
          <tr>
            <td colSpan={3}>{plural(vehicles.total, "vehicle", "vehicles")}</td>
            {rights.view && (
              <td className="r">
                {formatNumber(
                  rows.reduce(
                    (sum, vehicle) => sum + (vehicle.weeklyTarget ?? 0),
                    0,
                  ),
                )}
              </td>
            )}
            <td className="r">
              {formatNumber(
                rows.reduce(
                  (sum, vehicle) => sum + (vehicle.initialInvestment ?? 0),
                  0,
                ),
              )}
            </td>
            {rights.view && <td />}
            <td />
          </tr>
        }
        isEmpty={!rows.length}
        failed={Boolean(vehicles.error)}
        emptyMessage={
          filter === "all"
            ? "No vehicles yet. Add the first one above."
            : "No vehicles in this company yet."
        }
      >
        {rows.map((vehicle) => {
          const status = fleetStatus(vehicle, formatDateOnly);
          return (
            <Tr key={vehicle.id}>
              <Td label="Registration">
                <RegPlate>{vehicle.registration}</RegPlate>
                {status.tone !== "ok" && (
                  <>
                    {" "}
                    <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                  </>
                )}
              </Td>
              <Td label="Fleet number">{vehicle.fleetNumber ?? ""}</Td>
              <Td label="PSV company">{vehicle.companyName}</Td>
              {rights.view && (
                // Leaving the fleet ends the target: no "KES 0 a day" for a vehicle that no longer runs.
                <Td
                  label="Weekly target"
                  numeric
                  title={status.left ? "Target ended" : undefined}
                >
                  {status.left ? "—" : formatNumber(vehicle.weeklyTarget ?? 0)}
                  {vehicle.nextTarget && (
                    <span className="note wrap">
                      {formatNumber(vehicle.nextTarget.weeklyTarget)} from{" "}
                      {formatDateOnly(vehicle.nextTarget.startsOn)}
                    </span>
                  )}
                </Td>
              )}
              <Td label="Initial investment" numeric>
                {vehicle.initialInvestment
                  ? formatNumber(vehicle.initialInvestment)
                  : ""}
              </Td>
              {rights.view && (
                <Td label={scheduledLabel} numeric>
                  {vehicle.recurringItems ?? 0}
                </Td>
              )}
              <Td numeric>
                <div className="tacts">
                  {rights.target && (
                    <RowAction
                      aria-label={`Targets ${vehicle.registration}`}
                      disabled={!today}
                      onClick={() => setTargeting(vehicle.id)}
                    >
                      Targets
                    </RowAction>
                  )}
                  <RowAction
                    aria-label={`${rights.edit ? "Edit" : "Open"} ${vehicle.registration}`}
                    onClick={() => setEditing({ id: vehicle.id })}
                  >
                    {rights.edit ? "Edit" : "Open"}
                  </RowAction>
                </div>
              </Td>
            </Tr>
          );
        })}
      </DataTable>
      <ListPager list={vehicles} />
      {editing && (
        <VehicleEditor
          vehicle={editedVehicle}
          // A new vehicle starts on the filtered company only while it can be chosen: never on an archived one.
          defaultCompany={
            companies.some(
              (company) => company.id === filter && company.active !== false,
            )
              ? filter
              : ""
          }
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
      )}
      {targetedVehicle && today && (
        <TargetsDialog
          vehicle={targetedVehicle}
          today={today}
          onClose={() => setTargeting(null)}
          onChanged={vehicles.reload}
        />
      )}
    </>
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
      ? {
          label: `Left fleet ${formatDateOnly(vehicle.leftOn)}`,
          tone: "off",
          left: true,
        }
      : {
          label: `Leaves the fleet ${formatDateOnly(vehicle.leftOn)}`,
          tone: "warn",
          left: false,
        };
  return vehicle.active === false
    ? {
        label: `Joins ${formatDateOnly(vehicle.joinedOn)}`,
        tone: "neutral",
        left: false,
      }
    : { label: "Active", tone: "ok", left: false };
}

function CompanyFilter({
  value,
  companies,
  onChange,
}: {
  value: string;
  companies: CompanyChoice[];
  onChange: (companyId: string) => void;
}) {
  return (
    <>
      <label htmlFor="vehicle-filter" className="sr-only">
        Company
      </label>
      <SelectInput
        id="vehicle-filter"
        density="compact"
        inline
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="all">All companies</option>
        {companies.map((company) => (
          <option key={company.id} value={company.id}>
            {company.name}
          </option>
        ))}
      </SelectInput>
    </>
  );
}

// Someone who may not read the company options learns the companies from the vehicles listed, so each company seen
// stays a choice while another page or company is shown.
function useCompaniesSeen(rows: Vehicle[]) {
  const [seen, setSeen] = useState<Vehicle[]>([]);
  const unseen = rows.filter(
    (vehicle) => !seen.some((known) => known.companyId === vehicle.companyId),
  );
  if (unseen.length) setSeen([...seen, ...unseen]);
  return [...seen, ...unseen];
}

function companyChoices(
  vehicles: Vehicle[],
  companies?: Company[],
  options?: CompanyChoice[],
): CompanyChoice[] {
  const byId = new Map<string, CompanyChoice>();
  for (const company of companies ?? [])
    byId.set(company.id, {
      id: company.id,
      name: company.name,
      active: company.active,
    });
  for (const company of options ?? []) byId.set(company.id, company);
  // A company known only through its vehicles is one the server did not offer (archived, or not loaded yet): it
  // filters the list but is never offered for a vehicle to join.
  for (const vehicle of vehicles) {
    if (!byId.has(vehicle.companyId))
      byId.set(vehicle.companyId, {
        id: vehicle.companyId,
        name: vehicle.companyName,
        active: false,
      });
  }
  return [...byId.values()].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
}

const REGISTRATION = /^K[A-Z]{2}[0-9]{3}[A-Z]$/;

function normaliseRegistration(value: string) {
  const compact = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return REGISTRATION.test(compact)
    ? `${compact.slice(0, 3)} ${compact.slice(3)}`
    : null;
}

// Saving, retiring and restoring carry no typed reason: the server writes one for the change log.
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
  const rights = useVehicleRights();
  const { formatDateOnly, formatDateRange } = useFormats();
  const isNew = !vehicle;
  const [form, setForm] = useState<{
    registration: string;
    fleetNumber: string;
    companyId: string;
    initialInvestment: string;
    dayTargets: string[];
  }>({
    registration: vehicle?.registration ?? "",
    fleetNumber: vehicle?.fleetNumber ?? "",
    companyId: vehicle?.companyId ?? defaultCompany,
    initialInvestment: vehicle?.initialInvestment
      ? String(vehicle.initialInvestment)
      : "",
    dayTargets: EMPTY_TARGETS,
  });
  const [saveError, setSaveError] = useState("");
  const [lifecycleInput, setLifecycleDate] = useState<string | null>(
    vehicle?.leftOn ?? null,
  );
  const lifecycleDate = lifecycleInput ?? today ?? "";
  const [returnInput, setReturnDate] = useState<string | null>(null);
  const returnedOn = returnInput ?? today ?? "";
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<VehicleTab>("details");
  // Each tab needs its own permission: the details need the right to edit, the report the right to view vehicles.
  const tabs: { value: VehicleTab; label: string }[] = [
    ...(rights.edit ? [{ value: "details" as const, label: "Details" }] : []),
    ...(rights.view ? [{ value: "report" as const, label: "Report" }] : []),
    ...(can("commitments.view") || can("scheduled.view")
      ? [{ value: "scheduled" as const, label: "Scheduled items" }]
      : []),
    ...(can("invest.view") || can("reports.investment")
      ? [{ value: "investment" as const, label: "Investment" }]
      : []),
  ];
  const shownTab = tabs.some((option) => option.value === tab)
    ? tab
    : (tabs[0]?.value ?? "details");
  const companyName =
    companies.find((company) => company.id === form.companyId)?.name ??
    vehicle?.companyName;
  // Retired means it has a leave date; a vehicle that is not active without one joins after the business date.
  const retired = Boolean(vehicle?.leftOn);
  const joinsLater = Boolean(
    vehicle && !vehicle.leftOn && vehicle.active === false,
  );
  // Newest first: the stretch someone is most likely to be checking is the one that just ended.
  const away = [...(vehicle?.away ?? [])].reverse();

  async function retireVehicle() {
    if (!vehicle || retired) return;
    if (!lifecycleDate)
      return setSaveError("Choose the date it leaves the fleet.");
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
    if (!returnedOn)
      return setSaveError("Choose the date it returns to the fleet.");
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
    const fleetNumber = form.fleetNumber.trim();
    const investment = Number(form.initialInvestment) || 0;
    const dayTargets = targetFigures(form.dayTargets);
    const joinedOn = vehicle?.joinedOn ?? today;
    const problem = !registration
      ? "Enter the registration like KDN 204B."
      : !fleetNumber
        ? "Enter the fleet number."
        : !form.companyId
          ? "Choose the PSV company."
          : isNew && !hasEveryTarget(form.dayTargets)
            ? "Enter the target for every day."
            : !joinedOn
              ? "The business date has not loaded yet. Try again in a moment."
              : retired
                ? "Restore this vehicle before editing its details."
                : "";
    setSaveError(problem);
    if (problem || !registration || !joinedOn) return;
    if (
      !isNew &&
      vehicle.companyId === form.companyId &&
      (vehicle.fleetNumber ?? "") === fleetNumber &&
      (vehicle.initialInvestment ?? 0) === investment
    ) {
      toast("No changes to save.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        companyId: form.companyId,
        joinedOn,
        fleetNumber,
        initialInvestment: investment > 0 ? investment : null,
      };
      const result = isNew
        ? await vehiclesApi.create({
            ...body,
            registration,
            dayTargets,
          })
        : await vehiclesApi.update(vehicle.id, body);
      toast(
        isNew ? `${registration} added.` : `Changes saved for ${registration}.`,
      );
      onSaved({
        ...(vehicle ?? { targets: [], recurringItems: 0 }),
        id: result.id,
        registration,
        companyId: form.companyId,
        companyName: companyName ?? "",
        fleetNumber,
        initialInvestment: body.initialInvestment,
        ...(isNew
          ? {
              dayTargets,
              weeklyTarget: dayTargets.reduce((sum, figure) => sum + figure, 0),
            }
          : { weeklyTarget: vehicle.weeklyTarget }),
        joinedOn,
      });
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const registrationField = (
    <Field id="vehicle-registration" label="Registration">
      <TextInput
        value={form.registration}
        placeholder="KDN 204B"
        autoCapitalize="characters"
        onChange={(event) =>
          setForm({ ...form, registration: event.target.value.toUpperCase() })
        }
      />
    </Field>
  );
  const fleetField = (
    <Field id="vehicle-fleet" label="Fleet number">
      <TextInput
        value={form.fleetNumber}
        disabled={retired}
        onChange={(event) =>
          setForm({ ...form, fleetNumber: event.target.value })
        }
      />
    </Field>
  );
  const companyField = (
    <Field id="vehicle-company" label="PSV company">
      <SelectInput
        value={form.companyId}
        disabled={retired}
        onChange={(event) =>
          setForm({ ...form, companyId: event.target.value })
        }
      >
        <option value="">Choose a company</option>
        {companies
          .filter(
            (company) =>
              company.active !== false || company.id === vehicle?.companyId,
          )
          .map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
              {company.active === false ? " (archived)" : ""}
            </option>
          ))}
      </SelectInput>
    </Field>
  );
  const investmentField = (
    <Field id="vehicle-investment" label="Initial investment, KES">
      <CurrencyInput
        disabled={retired}
        value={form.initialInvestment}
        onChange={(event) =>
          setForm({ ...form, initialInvestment: event.target.value })
        }
      />
    </Field>
  );
  const details = (
    <form
      id="vehicle-form"
      className="contents"
      onSubmit={(event) => {
        event.preventDefault();
        void save();
      }}
    >
      <>
        {joinsLater && (
          <Note tone="info">
            Joins the fleet on {formatDateOnly(vehicle!.joinedOn)}, after the
            business date.
          </Note>
        )}
        {isNew ? (
          <>
            <FieldPair>
              {registrationField}
              {fleetField}
            </FieldPair>
            <FieldPair>
              {companyField}
              {investmentField}
            </FieldPair>
            <DayTargetGrid
              idPrefix="vehicle-day"
              values={form.dayTargets}
              onChange={(dayTargets) => setForm({ ...form, dayTargets })}
            />
          </>
        ) : (
          <>
            {fleetField}
            {companyField}
            {investmentField}
          </>
        )}
        {saveError && <ErrorText>{saveError}</ErrorText>}
        {vehicle && (
          <Card density="form">
            <CardHeader
              title="Fleet lifecycle"
              description="Leaving the fleet stops targets, scheduled item shares, and future report postings from that date."
            />
            {retired ? (
              <>
                <Hint>
                  {vehicle.active === false
                    ? "Left the fleet on"
                    : "Leaves the fleet on"}{" "}
                  {formatDateOnly(vehicle.leftOn!)}.
                </Hint>
                <Grid2 narrow>
                  <Field id="vehicle-returned-on" label="Returns to the fleet">
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
                  <Field id="vehicle-left-on" label="Leaves the fleet">
                    <TextInput
                      type="date"
                      min={vehicle.joinedOn}
                      max={today}
                      value={lifecycleDate}
                      onChange={(event) => setLifecycleDate(event.target.value)}
                    />
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
              <div className="f">
                <span className="flab">Time away from the fleet</span>
                <CardList>
                  {away.map((period) => (
                    <CardListItem
                      key={period.leftOn}
                      left={formatDateRange(
                        period.leftOn,
                        shiftDate(period.returnedOn, -1),
                      )}
                      rightSub={`Back on ${formatDateOnly(period.returnedOn)}`}
                    />
                  ))}
                </CardList>
              </div>
            )}
          </Card>
        )}
      </>
    </form>
  );
  const onDetails = isNew || shownTab === "details";
  return (
    <Dialog
      open
      size={isNew ? "md" : "lg"}
      title={
        isNew
          ? "New vehicle"
          : rights.edit
            ? "Edit vehicle"
            : vehicle.registration
      }
      subtitle={
        isNew
          ? undefined
          : `${rights.edit ? `${vehicleLabel(vehicle)} · ` : ""}${companyName}${retired ? " · Left the fleet" : joinsLater ? ` · Joins ${formatDateOnly(vehicle.joinedOn)}` : ""}`
      }
      onClose={onClose}
      footer={
        onDetails ? (
          <>
            <Button tone="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="vehicle-form"
              tone="ok"
              disabled={busy || retired}
            >
              Save
            </Button>
          </>
        ) : (
          <Button tone="outline" onClick={onClose}>
            Back
          </Button>
        )
      }
    >
      {isNew ? (
        details
      ) : (
        <Tabs
          id="vehicle"
          label={`About ${vehicleLabel(vehicle)}`}
          options={tabs}
          value={shownTab}
          onChange={setTab}
        >
          {shownTab === "details" && details}
          {shownTab === "report" && <VehicleReportCard vehicle={vehicle} />}
          {shownTab === "scheduled" && (
            <VehicleRecurringCard
              vehicle={vehicle}
              onOpen={onOpenRecurring}
              onAdd={onAddRecurring}
            />
          )}
          {shownTab === "investment" && (
            <VehicleInvestmentTab vehicle={vehicle} today={today} />
          )}
        </Tabs>
      )}
    </Dialog>
  );
}

// The vehicle report (contract C6), with the design's figures in the design's order. Postings are listed per item,
// each under its bucket or as savings. A revision that renamed the item or moved it to another bucket gets its own
// line, so no posting shows under a bucket it was not counted in.
function VehicleReportCard({ vehicle }: { vehicle: Vehicle }) {
  const { formatDateOnly, formatDateRange, kes, money } = useFormats();
  const [period, setPeriod] = useState<RevenueReportPeriod>("month");
  const report = useResource<VehicleReport>(
    `setup/vehicles/${vehicle.id}/report?period=${period}`,
  );
  const data = report.data;
  const grouped = [
    ...(data?.postings ?? [])
      .reduce((items, posting) => {
        const bucket = costBucket(posting);
        const key = JSON.stringify([
          posting.itemId,
          posting.name,
          posting.kind,
          bucket,
        ]);
        const item = items.get(key) ?? {
          id: key,
          name: posting.name,
          kind: posting.kind,
          bucket,
          total: 0,
          dates: [] as string[],
        };
        item.total += posting.amount;
        item.dates.push(posting.date);
        return items.set(key, item);
      }, new Map<string, { id: string; name: string; kind: number; bucket: ExpenseBucket | null; total: number; dates: string[] }>())
      .values(),
  ];
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
      />
      {report.error ? (
        <Hint>{report.error}</Hint>
      ) : report.loading || !data ? (
        <div role="status" aria-busy="true">
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
            <Stat
              label="Net contribution"
              value={money(data.net)}
              tone={data.net < 0 ? "bad" : undefined}
            />
            <Stat label="Savings set aside" value={kes(data.savings)} />
            <Stat
              label="After savings"
              value={money(data.afterSavings)}
              tone={data.afterSavings < 0 ? "bad" : undefined}
            />
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
  const canSee = can("commitments.view") || can("scheduled.view");
  const recurring = useStreamedList<RecurringItem>(
    canSee ? "setup/recurring" : null,
  );
  if (!canSee) return null;
  const today = appearance?.businessDate;
  const items = recurring.items.filter((item) =>
    item.allocations.some((allocation) => allocation.vehicleId === vehicle.id),
  );
  return (
    <Card>
      <CardHeader
        title={`Scheduled items for ${vehicleLabel(vehicle)}`}
        description="This vehicle's share of each scheduled expense or saving"
      />
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
            const allocation = item.allocations.find(
              (candidate) => candidate.vehicleId === vehicle.id,
            )!;
            const share = allocation.amount;
            const stopped =
              allocation.active === false ||
              Boolean(item.stoppedFrom) ||
              Boolean(today && item.end && item.end < today);
            return (
              <CardListItem
                key={item.id}
                left={
                  onOpen ? (
                    <RowButton onClick={() => onOpen(item.id)}>
                      {item.name}
                    </RowButton>
                  ) : (
                    item.name
                  )
                }
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
                rightSub={
                  item.allocations.length > 1
                    ? `of ${kes(item.activeAmount ?? item.amount)}`
                    : "each time"
                }
              />
            );
          })}
        </CardList>
      ) : (
        <Hint>Nothing scheduled for this vehicle yet.</Hint>
      )}
      {vehicle.active !== false &&
        (can("commitments.manage") || can("scheduled.add")) &&
        onAdd && (
          <CardAction onClick={() => onAdd(vehicle.id)}>
            Add scheduled item for {vehicleLabel(vehicle)}
          </CardAction>
        )}
    </Card>
  );
}
