"use client";

import { useEffect, useMemo, useState } from "react";
import type { RevenueCell, RevenueVehicle, RevenueWeek } from "@xcode/shared";
import { apiRequest, useResource } from "../lib/data";
import { formatDate, kes } from "../lib/format";
import { useSession } from "../lib/session-context";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  CardNote,
  CardValue,
  Choice,
  ChoiceField,
  CurrencyInput,
  Dialog,
  Field,
  PageHeader,
  SelectInput,
  StatusBadge,
  Toolbar,
} from "./ui";

const REASONS = ["Garage", "Arrest", "No Crew", "Other"] as const;
type Reason = (typeof REASONS)[number];

function dateLabel(value: string) {
  return formatDate(new Date(`${value}T00:00:00Z`));
}

function shiftDate(value: string, amount: number) {
  const date = new Date(`${value}T00:00:00Z`);
  date.setUTCDate(date.getUTCDate() + amount);
  return date.toISOString().slice(0, 10);
}

function statusTone(status: RevenueCell["status"]): "ok" | "warn" | "off" | "neutral" {
  if (status === "amount" || status === "reason") return "ok";
  if (status === "missing") return "warn";
  if (status === "none") return "off";
  return "neutral";
}

function statusLabel(cell: RevenueCell) {
  if (cell.status === "amount") return kes(cell.amount ?? 0);
  if (cell.status === "reason") return cell.reason ?? "No earnings";
  if (cell.status === "missing") return "Missing";
  if (cell.status === "future") return "Future";
  return "Not active";
}

export function RevenuePage() {
  const { session } = useSession();
  const [weekStart, setWeekStart] = useState("");
  const [companyId, setCompanyId] = useState("");
  const [editor, setEditor] = useState<{ vehicle: RevenueVehicle; cell: RevenueCell } | null>(null);
  const query = useMemo(() => {
    const params = new URLSearchParams();
    if (weekStart) params.set("weekStart", weekStart);
    if (companyId) params.set("companyId", companyId);
    const encoded = params.toString();
    return `setup/revenue${encoded ? `?${encoded}` : ""}`;
  }, [companyId, weekStart]);
  const week = useResource<RevenueWeek>(query);

  useEffect(() => {
    if (week.data && !weekStart) setWeekStart(week.data.weekStart);
  }, [week.data, weekStart]);

  const canView = Boolean(session?.permissions.includes("revenue.view"));
  if (!canView) {
    return (
      <section>
        <PageHeader title="Revenue" description="Your access does not include revenue records." />
      </section>
    );
  }

  const data = week.data;
  const previous = data ? shiftDate(data.weekStart, -7) : "";
  const next = data ? shiftDate(data.weekStart, 7) : "";
  const isCurrent = Boolean(data && data.weekStart >= data.currentWeekStart);

  return (
    <section>
      <PageHeader
        title="Revenue"
        description="Record either the day's revenue or why no revenue was earned. Missing days stay visible until resolved."
      />
      <Toolbar align="start">
        <div className="flex flex-wrap items-center gap-2">
          <Button tone="outline" disabled={!data || week.loading} onClick={() => setWeekStart(previous)}>
            Previous week
          </Button>
          <Button tone="outline" disabled={!data || week.loading || isCurrent} onClick={() => setWeekStart(next)}>
            Next week
          </Button>
        </div>
        <div className="min-w-56">
          <label htmlFor="revenue-company" className="sr-only">Company</label>
          <SelectInput
            id="revenue-company"
            density="compact"
            value={companyId}
            onChange={(event) => setCompanyId(event.target.value)}
          >
            <option value="">All companies</option>
            {data?.companies.map((company) => (
              <option key={company.id} value={company.id}>{company.name}</option>
            ))}
          </SelectInput>
        </div>
        {data && (
          <span className="self-center text-sm text-grey">
            {dateLabel(data.weekStart)} – {dateLabel(data.weekThrough)} · business date {dateLabel(data.businessDate)}
          </span>
        )}
      </Toolbar>

      {week.error && <Banner className="mt-4">{week.error}</Banner>}

      <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
        <Card>
          <CardHeader title="Recorded" description="Amount entries in this week" />
          <CardValue>{data ? kes(data.totalAmount) : "—"}</CardValue>
          <CardNote>{data ? `${data.percent ?? 0}% of expected ${kes(data.totalExpected)}` : "Loading revenue"}</CardNote>
        </Card>
        <Card>
          <CardHeader title="Expected" description="Dated target divided by seven" />
          <CardValue>{data ? kes(data.totalExpected) : "—"}</CardValue>
          <CardNote>Future and inactive days are excluded.</CardNote>
        </Card>
        <Card>
          <CardHeader title="Vehicles" description="In your permitted scope" />
          <CardValue>{data ? data.vehicles.length : "—"}</CardValue>
          <CardNote>Click a day to capture or correct it.</CardNote>
        </Card>
      </div>

      {week.loading && !data ? (
        <Card className="mt-4"><CardNote>Loading revenue records…</CardNote></Card>
      ) : !data || data.vehicles.length === 0 ? (
        <Card className="mt-4"><CardNote>No active or historical vehicles are in this scope.</CardNote></Card>
      ) : (
        <div className="mt-4 overflow-x-auto rounded-[14px] border border-card-line bg-white">
          <table className="min-w-[1120px] w-full border-collapse">
            <caption className="sr-only">Weekly revenue capture grid</caption>
            <thead>
              <tr>
                <th scope="col" className="sticky left-0 z-10 min-w-48 border-b border-card-line bg-paper px-4 py-3 text-left text-[13px] font-semibold text-grey">Vehicle</th>
                {data.vehicles[0].days.map((cell) => (
                  <th key={cell.date} scope="col" className="min-w-28 border-b border-card-line bg-paper px-3 py-3 text-left text-[13px] font-semibold text-grey">
                    {dateLabel(cell.date)}
                    <span className="block font-normal">Expected {kes(cell.expected)}</span>
                  </th>
                ))}
                <th scope="col" className="min-w-36 border-b border-card-line bg-paper px-4 py-3 text-right text-[13px] font-semibold text-grey">Week total</th>
              </tr>
            </thead>
            <tbody>
              {data.vehicles.map((vehicle) => (
                <tr key={vehicle.id} className="border-b border-divider last:border-b-0">
                  <td className="sticky left-0 z-10 border-r border-divider bg-white px-4 py-3 align-top">
                    <strong className="block text-[15px]">{vehicle.registration}</strong>
                    <span className="block text-[13px] text-grey">{vehicle.companyName}</span>
                    {vehicle.earliestMissing && (
                      <span className="mt-1 block text-xs text-amber-text">Fill from {dateLabel(vehicle.earliestMissing)}</span>
                    )}
                  </td>
                  {vehicle.days.map((cell) => (
                    <td key={cell.date} className="border-divider px-3 py-3 align-top">
                      {cell.canEdit ? (
                        <button
                          type="button"
                          className="min-h-12 w-full rounded-lg text-left hover:bg-hover focus:outline-3 focus:outline-offset-1 focus:outline-blue/30"
                          aria-label={`${vehicle.registration}, ${dateLabel(cell.date)}: ${statusLabel(cell)}`}
                          onClick={() => setEditor({ vehicle, cell })}
                        >
                          <CellValue cell={cell} />
                        </button>
                      ) : (
                        <CellValue cell={cell} />
                      )}
                    </td>
                  ))}
                  <td className="border-divider px-4 py-3 text-right align-top tabular-nums">
                    <strong className="block">{kes(vehicle.totalAmount)}</strong>
                    <span className="block text-[13px] text-grey">of {kes(vehicle.totalExpected)}</span>
                    <span className={vehicle.percent !== null && vehicle.percent < 100 ? "block text-[13px] text-red" : "block text-[13px] text-green"}>
                      {vehicle.percent === null ? "No target" : `${vehicle.percent}%`}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="bg-paper font-semibold">
                <th scope="row" className="px-4 py-3 text-left">Total</th>
                {data.vehicles[0].days.map((cell) => (
                  <td key={cell.date} className="px-3 py-3 tabular-nums">
                    {kes(data.vehicles.reduce((sum, vehicle) => sum + (vehicle.days.find((item) => item.date === cell.date)?.amount ?? 0), 0))}
                  </td>
                ))}
                <td className="px-4 py-3 text-right tabular-nums">{kes(data.totalAmount)}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}

      {editor && (
        <RevenueEditor
          key={`${editor.vehicle.id}-${editor.cell.date}`}
          vehicle={editor.vehicle}
          cell={editor.cell}
          canChooseReason={Boolean(session?.permissions.includes("revenue.no_earnings"))}
          onClose={() => setEditor(null)}
          onSaved={() => {
            setEditor(null);
            week.reload();
          }}
        />
      )}
    </section>
  );
}

function CellValue({ cell }: { cell: RevenueCell }) {
  return (
    <span className="flex flex-col gap-1">
      <StatusBadge tone={statusTone(cell.status)}>{statusLabel(cell)}</StatusBadge>
      {cell.editedAfterCapture && <small className="text-xs text-grey">Edited after capture</small>}
    </span>
  );
}

function RevenueEditor({
  vehicle,
  cell,
  canChooseReason,
  onClose,
  onSaved,
}: {
  vehicle: RevenueVehicle;
  cell: RevenueCell;
  canChooseReason: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [amount, setAmount] = useState(cell.amount === null ? "" : String(cell.amount));
  const [reason, setReason] = useState<Reason | "">((cell.reason as Reason | null) ?? "");
  const [note, setNote] = useState(cell.note ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setError("");
    const text = amount.replace(/,/g, "").trim();
    const numeric = text ? Number(text) : null;
    if (text && (!Number.isFinite(numeric) || numeric <= 0)) {
      setError("Enter a positive revenue amount.");
      return;
    }
    if (numeric !== null && reason) {
      setError("Choose either a revenue amount or a no-earnings reason.");
      return;
    }
    if (numeric === null && !reason) {
      setError("Enter revenue or choose why there was no revenue.");
      return;
    }
    if (reason === "Other" && !note.trim()) {
      setError("Explain what happened when choosing Other.");
      return;
    }
    setSaving(true);
    try {
      await apiRequest(`setup/revenue/${vehicle.id}/${cell.date}`, {
        method: "PUT",
        body: JSON.stringify({
          amount: numeric,
          reason: reason || null,
          note: reason === "Other" ? note.trim() : null,
        }),
      });
      onSaved();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "The revenue record could not be saved.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open title={`${vehicle.registration} · ${dateLabel(cell.date)}`} onClose={onClose}>
      <div className="flex flex-col gap-4">
        <p className="m-0 text-sm text-grey">Expected for this date: {kes(cell.expected)}. Earlier missing days must be handled first.</p>
        <Field id="revenue-amount" label="Revenue amount" hint="Leave empty when recording no earnings.">
          <CurrencyInput
            value={amount}
            onChange={(event) => {
              setAmount(event.target.value);
              if (event.target.value) setReason("");
            }}
            disabled={Boolean(reason)}
          />
        </Field>
        <ChoiceField label="No earnings reason" hint={!canChooseReason ? "Your access does not include no-earnings reasons." : undefined}>
          {REASONS.map((item) => (
            <Choice
              key={item}
              type="radio"
              name="revenue-reason"
              label={item}
              value={item}
              checked={reason === item}
              disabled={!canChooseReason || Boolean(amount)}
              onChange={() => {
                setReason(item);
                setAmount("");
                if (item !== "Other") setNote("");
              }}
            />
          ))}
        </ChoiceField>
        {reason === "Other" && (
          <Field id="revenue-note" label="What happened?" hint="Up to 80 characters.">
            <input
              id="revenue-note"
              className="h-12 w-full rounded-[10px] border border-line bg-white px-3 text-base focus:border-blue focus:outline-3 focus:outline-offset-1 focus:outline-blue/30"
              maxLength={80}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </Field>
        )}
        {error && <Banner>{error}</Banner>}
        <div className="flex flex-wrap justify-end gap-3">
          <Button tone="outline" onClick={onClose} disabled={saving}>Cancel</Button>
          <Button onClick={() => void save()} disabled={saving}>{saving ? "Saving…" : "Save revenue"}</Button>
        </div>
      </div>
    </Dialog>
  );
}
