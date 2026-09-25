"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { requestSetup } from "./requestSetup";

type Vehicle = { id: string; companyId: string; companyName: string; registration: string; joinedOn: string; weeklyTarget: number };

type RecurringItem = {
  id: string;
  name: string;
  kind: number;
  category?: number;
  amount: number;
  frequency: number;
  day?: number | null;
  lastDay: boolean;
  start: string;
  end?: string | null;
  allocations: { vehicleId: string; amount: number }[];
};

type Props = {
  item?: RecurringItem;
  vehicles: Vehicle[];
  onCancel: () => void;
  onSaved: () => Promise<void>;
};

export function RecurringEditor({ item, vehicles, onCancel, onSaved }: Props) {
  const isNew = !item;
  const [name, setName] = useState(item?.name || "");
  const [kind, setKind] = useState(item?.kind || 1);
  const [category, setCategory] = useState(item?.category || 4);
  const [amount, setAmount] = useState(String(item?.amount || ""));
  const [frequency, setFrequency] = useState(item?.frequency || 3);
  const [day, setDay] = useState(String(item?.day || 1));
  const [lastDay, setLastDay] = useState(item?.lastDay || false);
  const [start, setStart] = useState(item?.start || "2026-09-25");
  const [end, setEnd] = useState(item?.end || "");
  const [selected, setSelected] = useState<string[]>(item?.allocations.map((allocation) => allocation.vehicleId) || []);
  const [error, setError] = useState("");
  const total = Number(amount) || 0;
  const share = selected.length ? total / selected.length : 0;
  const allocationTotal = share * selected.length;

  async function save() {
    if (!name.trim() || total <= 0 || !start || !selected.length || (frequency === 3 && !lastDay && Number(day) > 28)) {
      setError("Enter a name, amount, period, and at least one vehicle.");
      return;
    }
    try {
      const body = {
        name: name.trim(),
        kind,
        category: kind === 1 ? category : null,
        amount: total,
        frequency,
        day: frequency === 1 || (frequency === 3 && lastDay) ? null : Number(day),
        lastDay,
        start,
        end: end || null,
        allocations: selected.map((vehicleId) => ({ vehicleId, amount: share })),
        reason: isNew ? "Added recurring item" : "Updated recurring item",
      };
      await requestSetup(isNew ? "recurring" : `recurring/${item!.id}`, {
        method: isNew ? "POST" : "PUT",
        body: JSON.stringify(body),
      });
      await onSaved();
    } catch (value) {
      setError((value as Error).message);
    }
  }

  async function stop() {
    if (!item) return;
    try {
      await requestSetup(`recurring/${item.id}/stop`, {
        method: "POST",
        body: JSON.stringify({ confirmed: true, reason: "Stopped recurring item" }),
      });
      await onSaved();
    } catch (value) {
      setError((value as Error).message);
    }
  }

  return (
    <section className="form setup-detail">
      <div className="page-head"><div><p className="eyebrow">Organization administration</p><h1>{isNew ? "Add recurring cost or saving" : name}</h1><p className="muted">{isNew ? "It posts to the vehicles you choose on every due date in its period." : "Recurring item details and future postings."}</p></div></div>
      {error && <p className="error-box" role="alert">{error}</p>}
      <article className="card">
        <header><h2 className="card-title">What it is</h2></header>
        {isNew && <div className="quick-picks" aria-label="Quick picks"><button type="button" onClick={() => { setName("Loan repayment"); setCategory(4); }}>Loan repayment</button><button type="button" onClick={() => { setName("Insurance"); setCategory(4); }}>Insurance</button><button type="button" onClick={() => { setName("Savings"); setKind(2); setFrequency(2); }}>Savings</button></div>}
        <div className="grid2">
          <Field label="Name" id="recurring-name"><input id="recurring-name" value={name} placeholder="For example Loan repayment" onChange={(event) => setName(event.target.value)} /></Field>
          <RadioGroup label="Type" name="recurring-kind" value={kind} options={[[1, "Cost"], [2, "Savings"]]} onChange={setKind} />
          {kind === 1 && <Field label="Cost type" id="recurring-category"><select id="recurring-category" value={category} onChange={(event) => setCategory(Number(event.target.value))}><option value="1">Running costs</option><option value="2">Repairs and upkeep</option><option value="3">Crew costs</option><option value="4">Fixed commitments</option></select></Field>}
          <Field label="Amount each time" id="recurring-amount"><input id="recurring-amount" type="number" min="1" value={amount} onChange={(event) => setAmount(event.target.value)} /><p className="hint">The total. Split it across vehicles below.</p></Field>
        </div>
      </article>
      <article className="card">
        <header><h2 className="card-title">How often</h2></header>
        <RadioGroup label="Frequency" name="recurring-frequency" value={frequency} options={[[1, "Every day"], [2, "Every week"], [3, "Every month"]]} onChange={setFrequency} />
        <div className="grid2">
          {frequency !== 1 && <Field label={frequency === 2 ? "Day of week" : "Day of month"} id="recurring-day"><input id="recurring-day" type="number" min="1" max="28" value={day} disabled={frequency === 3 && lastDay} onChange={(event) => setDay(event.target.value)} /></Field>}
          <Field label="Starts" id="recurring-start"><input id="recurring-start" type="date" value={start} onChange={(event) => setStart(event.target.value)} /></Field>
          <Field label="Ends" id="recurring-end"><input id="recurring-end" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />{frequency === 3 && <label className="recurring-end-check"><input type="checkbox" checked={lastDay} onChange={(event) => setLastDay(event.target.checked)} /> <span>Last day of month</span></label>}</Field>
        </div>
      </article>
      <article className="card">
        <header><h2 className="card-title">Vehicles</h2><p className="card-sub">Split the amount across one or more vehicles.</p></header>
        <div className="vehicle-check-grid">{vehicles.map((vehicle) => <label className="check" key={vehicle.id}><input type="checkbox" checked={selected.includes(vehicle.id)} onChange={(event) => setSelected(event.target.checked ? [...selected, vehicle.id] : selected.filter((id) => id !== vehicle.id))} />{vehicle.registration}</label>)}</div>
        <p className={`balance ${selected.length && total ? "ok" : ""}`} role="status"><span>Allocated KES {allocationTotal.toLocaleString()} of KES {total.toLocaleString()}</span><span>{selected.length && total ? "Balanced" : "Choose vehicles and enter an amount"}</span></p>
      </article>
      <article className="card"><header><h2 className="card-title">What will post</h2><p className="card-sub">Worked out for you</p></header><p className="hint">{total && selected.length ? `KES ${total.toLocaleString()} across ${selected.length} vehicle${selected.length === 1 ? "" : "s"} starting ${start}.` : "Enter the amount and choose vehicles to see the postings."}</p></article>
      <div className="form-actions"><button className="btn-pill" onClick={() => void save()}>{isNew ? "Add" : "Save changes"}</button><button className="btn-pill outline" onClick={onCancel}>{isNew ? "Cancel" : "Back"}</button>{item && <button className="btn-pill danger" onClick={() => void stop()}>Stop from today</button>}</div>
    </section>
  );
}

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return <div className="f"><label htmlFor={id}>{label}</label>{children}</div>;
}

function RadioGroup({ label, name, value, options, onChange }: { label: string; name: string; value: number; options: [number, string][]; onChange: (value: number) => void }) {
  return <fieldset className="radio-field"><legend>{label}</legend><div className="option-group" role="radiogroup" aria-label={label}>{options.map(([option, text]) => <label className="option" key={option}><input type="radio" name={name} value={option} checked={value === option} onChange={() => onChange(option)} /><span>{text}</span></label>)}</div></fieldset>;
}
