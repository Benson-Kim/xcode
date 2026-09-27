"use client";

import { useState } from "react";
import { requestSetup } from "../requestSetup";
import type { Page } from "../../lib/types";
import { useSetupData } from "../../lib/useSetupData";
import { useSession } from "../../lib/session-context";
import { kes, plural } from "../../lib/format";
import { formatDateOnly, formatDateRange, recurringFrequency, todayDateOnly } from "../recurringPresentation";
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
  PageHeader,
  RowButton,
  SegmentedControl,
  SelectInput,
  Spacer,
  Stat,
  StatGrid,
  StatGridSkeleton,
  SubHeading,
  Td,
  TextInput,
  Toolbar,
  Tr,
  useToast,
} from "../ui";
import { LIST, recurringCategoryNames, type Company, type RecurringItem, type Vehicle, type VehicleReport } from "./shared";

type CompanyChoice = { id: string; name: string };

export function VehiclesPage({
  onOpenRecurring,
  onAddRecurring,
}: {
  onOpenRecurring?: (itemId: string) => void;
  onAddRecurring?: (vehicleId: string) => void;
}) {
  const { can } = useSession();
  const vehicles = useSetupData<Page<Vehicle>>(`vehicles${LIST}`);
  // Vehicle managers may not manage companies; the vehicles they see name their companies too.
  const companyList = useSetupData<Page<Company>>(can("companies.manage") ? `companies${LIST}` : null);
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState<Vehicle | "new" | null>(null);
  const rows = vehicles.data?.items ?? [];
  const companies = companyChoices(rows, companyList.data?.items);

  if (editing)
    return (
      <VehicleEditor
        vehicle={editing === "new" ? undefined : editing}
        defaultCompany={filter === "all" ? "" : filter}
        companies={companies}
        onOpenRecurring={onOpenRecurring}
        onAddRecurring={onAddRecurring}
        onClose={() => setEditing(null)}
        onSaved={(saved) => {
          vehicles.reload();
          setEditing(saved);
        }}
      />
    );

  const visible = rows.filter((vehicle) => filter === "all" || vehicle.companyId === filter);
  return (
    <section>
      <PageHeader
        title="Vehicles"
        description="Registration, company, weekly target, and the recurring costs and savings that post to each vehicle."
      />
      {vehicles.error && <Banner className="mt-5">{vehicles.error}</Banner>}
      <Toolbar>
        <label htmlFor="vehicle-filter" className="text-[13px] text-grey">
          Company
        </label>
        <SelectInput id="vehicle-filter" density="compact" inline value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">All companies</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </SelectInput>
        {!vehicles.loading && <Hint>{plural(visible.length, "vehicle", "vehicles")}</Hint>}
        <Spacer />
        <Button onClick={() => setEditing("new")}>Add vehicle</Button>
      </Toolbar>
      <DataTable
        columns={[
          { label: "Registration" },
          { label: "Company" },
          { label: "Weekly target", numeric: true },
          { label: "In the fleet from" },
          { label: "Recurring items" },
        ]}
        loading={vehicles.loading}
        loadingLabel="Loading vehicles"
        isEmpty={!visible.length}
        emptyMessage={filter === "all" ? "No vehicles yet. Add the first one above." : "No vehicles in this company yet."}
      >
        {visible.map((vehicle) => (
          <Tr key={vehicle.id}>
            <Td label="Registration">
              <RowButton onClick={() => setEditing(vehicle)}>{vehicle.registration}</RowButton>
            </Td>
            <Td label="Company">{vehicle.companyName}</Td>
            <Td label="Weekly target" numeric>
              {kes(vehicle.weeklyTarget)}
              <CellNote>About {kes(Math.round(vehicle.weeklyTarget / 7))} a day</CellNote>
            </Td>
            <Td label="In the fleet from">{formatDateOnly(vehicle.joinedOn)}</Td>
            <Td label="Recurring items">{vehicle.recurringItems ?? 0}</Td>
          </Tr>
        ))}
      </DataTable>
    </section>
  );
}

function companyChoices(vehicles: Vehicle[], companies?: Company[]): CompanyChoice[] {
  const byId = new Map<string, string>();
  for (const company of companies ?? []) byId.set(company.id, company.name);
  for (const vehicle of vehicles) if (!byId.has(vehicle.companyId)) byId.set(vehicle.companyId, vehicle.companyName);
  return [...byId].map(([id, name]) => ({ id, name })).sort((left, right) => left.name.localeCompare(right.name));
}

const REGISTRATION = /^K[A-Z]{2}[0-9]{3}[A-Z]$/;

function normaliseRegistration(value: string) {
  const compact = value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  return REGISTRATION.test(compact) ? `${compact.slice(0, 3)} ${compact.slice(3)}` : null;
}

type Errors = Partial<Record<"registration" | "companyId" | "weeklyTarget" | "joinedOn", string>>;

function VehicleEditor({
  vehicle,
  defaultCompany,
  companies,
  onOpenRecurring,
  onAddRecurring,
  onClose,
  onSaved,
}: {
  vehicle?: Vehicle;
  defaultCompany: string;
  companies: CompanyChoice[];
  onOpenRecurring?: (itemId: string) => void;
  onAddRecurring?: (vehicleId: string) => void;
  onClose: () => void;
  onSaved: (vehicle: Vehicle) => void;
}) {
  const toast = useToast();
  const isNew = !vehicle;
  const [form, setForm] = useState({
    registration: vehicle?.registration ?? "",
    companyId: vehicle?.companyId ?? defaultCompany,
    weeklyTarget: vehicle ? String(vehicle.weeklyTarget) : "",
    joinedOn: vehicle?.joinedOn ?? todayDateOnly(),
  });
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [busy, setBusy] = useState(false);
  const weekly = Number(form.weeklyTarget) || 0;
  const companyName = companies.find((company) => company.id === form.companyId)?.name ?? vehicle?.companyName;

  async function save() {
    const registration = isNew ? normaliseRegistration(form.registration) : vehicle.registration;
    const next: Errors = {};
    if (isNew && !form.registration.trim()) next.registration = "Enter the registration number.";
    else if (!registration) next.registration = "Use the Kenyan format, for example KDA 482M.";
    if (!form.companyId) next.companyId = "Choose the PSV company.";
    if (weekly <= 0) next.weeklyTarget = "Enter the weekly target in KES.";
    if (!form.joinedOn) next.joinedOn = "Enter the date it joined the fleet.";
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length || !registration) return;
    if (!isNew && vehicle.companyId === form.companyId && vehicle.weeklyTarget === weekly && vehicle.joinedOn === form.joinedOn) {
      toast("No changes to save.");
      return;
    }
    setBusy(true);
    try {
      const result = await requestSetup<{ id: string }>(isNew ? "vehicles" : `vehicles/${vehicle.id}`, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify({
          registration,
          companyId: form.companyId,
          weeklyTarget: weekly,
          joinedOn: form.joinedOn,
          reason: isNew ? `Added vehicle ${registration}` : `Updated vehicle ${registration}`,
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
        joinedOn: form.joinedOn,
      });
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const history = [...(vehicle?.targets ?? [])].sort((left, right) => right.effectiveFrom.localeCompare(left.effectiveFrom) || right.revision - left.revision);
  return (
    <section>
      <PageHeader
        title={isNew ? "Add vehicle" : vehicle.registration}
        description={isNew ? "It shows on reports and the dashboard straight away." : companyName}
      />
      <FormLayout>
        <ErrorSummary count={Object.keys(errors).length} />
        {saveError && <Banner>{saveError}</Banner>}
        <Card density="form">
          <CardHeader title="Vehicle" />
          <Grid2>
            <Field
              id="vehicle-registration"
              label="Registration number"
              error={errors.registration}
              hint={isNew ? "Kenyan format, for example KDA 482M." : "A registration cannot change. Add the vehicle again if it is re-registered."}
            >
              <TextInput
                value={form.registration}
                disabled={!isNew}
                placeholder="KDA 482M"
                autoCapitalize="characters"
                onChange={(event) => setForm({ ...form, registration: event.target.value.toUpperCase() })}
              />
            </Field>
            <Field id="vehicle-company" label="PSV company" error={errors.companyId}>
              <SelectInput value={form.companyId} onChange={(event) => setForm({ ...form, companyId: event.target.value })}>
                <option value="">Choose a company</option>
                {companies.map((company) => (
                  <option key={company.id} value={company.id}>
                    {company.name}
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
              <CurrencyInput min="1" step="1" value={form.weeklyTarget} onChange={(event) => setForm({ ...form, weeklyTarget: event.target.value })} />
            </Field>
            <Field id="vehicle-joined" label="In the fleet from" error={errors.joinedOn} hint="Missing revenue days are only counted from this date.">
              <TextInput type="date" value={form.joinedOn} onChange={(event) => setForm({ ...form, joinedOn: event.target.value })} />
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
        <FormActions>
          <Button disabled={busy} onClick={() => void save()}>
            {isNew ? "Add vehicle" : "Save changes"}
          </Button>
          <Button tone="outline" onClick={onClose}>
            Cancel
          </Button>
        </FormActions>
        {vehicle && <VehicleReportCard vehicle={vehicle} />}
        {vehicle && <VehicleRecurringCard vehicle={vehicle} onOpen={onOpenRecurring} onAdd={onAddRecurring} />}
      </FormLayout>
    </section>
  );
}

const categories = [1, 2, 3, 4];

function VehicleReportCard({ vehicle }: { vehicle: Vehicle }) {
  const [period, setPeriod] = useState<"week" | "month">("month");
  const report = useSetupData<VehicleReport>(`vehicles/${vehicle.id}/report?period=${period}`);
  const postings = report.data?.postings ?? [];
  const byCategory = (category: number) =>
    postings.filter((posting) => posting.kind === 1 && posting.category === category).reduce((sum, posting) => sum + posting.amount, 0);
  const grouped = [...postings.reduce((items, posting) => {
    const item = items.get(posting.itemId) ?? { name: posting.name, kind: posting.kind, category: posting.category, total: 0, dates: [] as string[] };
    item.total += posting.amount;
    item.dates.push(posting.date);
    return items.set(posting.itemId, item);
  }, new Map<string, { name: string; kind: number; category?: number | null; total: number; dates: string[] }>()).values()];
  return (
    <Card>
      <CardHeader
        title="Vehicle report"
        description={`${period === "week" ? "This week" : "This month"}${report.data ? `, ${formatDateRange(report.data.from, report.data.through)}` : ""}. Recurring items post on their own dates.`}
      />
      <SegmentedControl
        label="Report period"
        options={[
          { value: "week", label: "This week" },
          { value: "month", label: "This month" },
        ]}
        value={period}
        onChange={setPeriod}
      />
      {report.error ? (
        <Hint>{report.error}</Hint>
      ) : report.loading || !report.data ? (
        <div role="status" aria-busy="true" className="flex flex-col gap-2.5">
          <span className="sr-only">Loading the vehicle report</span>
          <StatGridSkeleton count={5} />
          <ListSkeleton rows={2} />
        </div>
      ) : (
        <>
          <StatGrid>
            {categories.map((category) => (
              <Stat key={category} label={recurringCategoryNames[category]} value={kes(byCategory(category))} />
            ))}
            <Stat label="Savings set aside" value={kes(report.data.savings)} />
          </StatGrid>
          <SubHeading>Recurring postings in this period</SubHeading>
          {grouped.length ? (
            <CardList>
              {grouped.map((item) => (
                <CardListItem
                  key={item.name + item.dates[0]}
                  left={item.name}
                  leftSub={`${item.kind === 2 ? "Savings" : recurringCategoryNames[item.category ?? 4]}. ${
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
  const recurring = useSetupData<Page<RecurringItem>>(can("commitments.view") ? `recurring${LIST}` : null);
  if (!can("commitments.view")) return null;
  const today = todayDateOnly();
  const items = (recurring.data?.items ?? []).filter((item) => item.allocations.some((allocation) => allocation.vehicleId === vehicle.id));
  return (
    <Card>
      <CardHeader title={`Recurring costs and savings for ${vehicle.registration}`} description="This vehicle's share of each item" />
      {recurring.loading ? (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading recurring items</span>
          <ListSkeleton rows={2} />
        </div>
      ) : recurring.error ? (
        <Hint>{recurring.error}</Hint>
      ) : items.length ? (
        <CardList>
          {items.map((item) => {
            const share = item.allocations.find((allocation) => allocation.vehicleId === vehicle.id)!.amount;
            const stopped = Boolean(item.stoppedFrom) || Boolean(item.end && item.end < today);
            return (
              <CardListItem
                key={item.id}
                left={onOpen ? <RowButton onClick={() => onOpen(item.id)}>{item.name}</RowButton> : item.name}
                leftSub={`${recurringFrequency(item)}${stopped ? ". Stopped" : ""}`}
                right={kes(share)}
                rightSub={item.allocations.length > 1 ? `of ${kes(item.amount)}` : "each time"}
              />
            );
          })}
        </CardList>
      ) : (
        <Hint>None yet.</Hint>
      )}
      {can("commitments.manage") && onAdd && (
        <CardAction onClick={() => onAdd(vehicle.id)}>Add recurring cost or saving for {vehicle.registration}</CardAction>
      )}
    </Card>
  );
}
