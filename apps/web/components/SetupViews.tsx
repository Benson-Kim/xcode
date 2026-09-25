"use client";

import { useEffect, useState } from "react";
import { requestSetup } from "./requestSetup";
import { RecurringEditor as ReferenceRecurringEditor } from "./RecurringEditor";
import type { Page } from "./setupTypes";

type Company = { id: string; name: string; vehicleCount: number };
type Vehicle = {
  id: string;
  companyId: string;
  companyName: string;
  registration: string;
  joinedOn: string;
  weeklyTarget: number;
};
type HistoryRow = {
  version: number;
  section: string;
  entityId: string;
  before: string | null;
  after: string;
  reason: string;
  occurredAt: string;
  actorId: string;
};

function SetupError({ message }: { message: string }) {
  return message ? (
    <p className="error-box" role="alert">
      {message}
    </p>
  ) : null;
}

export function CompaniesView() {
  const [companies, setCompanies] = useState<Company[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");
  const [fieldError, setFieldError] = useState("");
  async function reload() {
    try {
      setCompanies((await requestSetup<Page<Company>>("companies")).items);
    } catch (value) {
      setError((value as Error).message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  async function add() {
    if (!name.trim()) {
      setFieldError("Enter the company name.");
      return;
    }
    try {
      await requestSetup("companies", {
        method: "POST",
        body: JSON.stringify({
          name: name.trim(),
          reason: "Added PSV company",
        }),
      });
      setName("");
      setFieldError("");
      setError("");
      await reload();
    } catch (value) {
      setFieldError((value as Error).message);
    }
  }
  function startRename(company: Company) {
    setEditingId(company.id);
    setEditingName(company.name);
    setFieldError("");
  }
  function cancelRename() {
    setEditingId(null);
    setEditingName("");
    setFieldError("");
  }
  async function saveRename(company: Company) {
    if (!editingName.trim()) {
      setFieldError("Enter the company name.");
      return;
    }
    if (editingName.trim() === company.name) {
      cancelRename();
      return;
    }
    try {
      await requestSetup(`companies/${company.id}`, {
        method: "PUT",
        body: JSON.stringify({
          name: editingName.trim(),
          reason: "Updated PSV company name",
        }),
      });
      cancelRename();
      setError("");
      await reload();
    } catch (value) {
      setFieldError((value as Error).message);
    }
  }
  return (
    <section>
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization administration</p>
          <h1>PSV companies</h1>
          <p className="muted">Every vehicle belongs to one company.</p>
        </div>
      </div>
      <SetupError message={error} />
      <div className="toolbar company-toolbar">
        <div className="inline-field">
          <label htmlFor="new-company">New PSV company</label>
          <input
            id="new-company"
            aria-label="New PSV company"
            placeholder="Company name"
            value={name}
            aria-invalid={Boolean(fieldError) && !editingId}
            onChange={(event) => {
              setName(event.target.value);
              setFieldError("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") void add();
            }}
          />
          {fieldError && !editingId && (
            <p className="field-error">{fieldError}</p>
          )}
        </div>
        <button className="btn-pill" onClick={() => void add()}>
          Add company
        </button>
      </div>
      <div className="table-card">
        <table className="list">
          <thead>
            <tr>
              <th>Company</th>
              <th className="num">Vehicles</th>
              <th aria-label="Actions" />
            </tr>
          </thead>
          <tbody>
            {companies.length ? (
              companies.map((company) =>
                editingId === company.id ? (
                  <tr key={company.id}>
                    <td colSpan={3}>
                      <div className="inline-edit-row">
                        <div className="inline-field">
                          <label htmlFor={`rename-company-${company.id}`}>
                            New name
                          </label>
                          <input
                            id={`rename-company-${company.id}`}
                            value={editingName}
                            aria-invalid={Boolean(fieldError)}
                            onChange={(event) => {
                              setEditingName(event.target.value);
                              setFieldError("");
                            }}
                            onKeyDown={(event) => {
                              if (event.key === "Enter")
                                void saveRename(company);
                            }}
                          />
                          {fieldError && (
                            <p className="field-error">{fieldError}</p>
                          )}
                        </div>
                        <button
                          className="btn-pill"
                          onClick={() => void saveRename(company)}
                        >
                          Save
                        </button>
                        <button
                          className="btn-pill outline"
                          onClick={cancelRename}
                        >
                          Cancel
                        </button>
                      </div>
                    </td>
                  </tr>
                ) : (
                  <tr key={company.id}>
                    <td>
                      <strong>{company.name}</strong>
                    </td>
                    <td className="num">{company.vehicleCount}</td>
                    <td>
                      <button
                        className="row-btn"
                        onClick={() => startRename(company)}
                      >
                        Rename
                      </button>
                    </td>
                  </tr>
                ),
              )
            ) : (
              <tr>
                <td className="empty-row" colSpan={3}>
                  No companies yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function VehiclesView() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [companies, setCompanies] = useState<Company[]>([]);
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState<Vehicle | null>(null);
  const [error, setError] = useState("");
  async function reload() {
    try {
      const [vehiclePage, companyPage] = await Promise.all([
        requestSetup<Page<Vehicle>>("vehicles"),
        requestSetup<Page<Company>>("companies"),
      ]);
      setVehicles(vehiclePage.items);
      setCompanies(companyPage.items);
    } catch (value) {
      setError((value as Error).message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  if (editing) {
    return (
      <VehicleEditor
        vehicle={editing.id ? editing : undefined}
        companies={companies}
        onCancel={() => setEditing(null)}
        onSaved={async (id) => {
          setEditing(null);
          await reload();
          const next = id
            ? vehicles.find((vehicle) => vehicle.id === id)
            : undefined;
          if (!next) setError("");
        }}
      />
    );
  }
  const visible = vehicles.filter(
    (vehicle) => filter === "all" || vehicle.companyId === filter,
  );
  return (
    <section>
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization administration</p>
          <h1>Vehicles</h1>
          <p className="muted">
            Registration, company, weekly target, and the recurring costs and
            savings that post to each vehicle.
          </p>
        </div>
      </div>
      <SetupError message={error} />
      <div className="toolbar vehicle-toolbar">
        <label htmlFor="vehicle-filter">Company</label>
        <select
          id="vehicle-filter"
          aria-label="Company"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
        >
          <option value="all">All companies</option>
          {companies.map((company) => (
            <option key={company.id} value={company.id}>
              {company.name}
            </option>
          ))}
        </select>
        <span className="hint">
          {visible.length} {visible.length === 1 ? "vehicle" : "vehicles"}
        </span>
        <button
          className="btn-pill"
          onClick={() =>
            setEditing({
              id: "",
              companyId: companies[0]?.id || "",
              companyName: "",
              registration: "",
              joinedOn: "",
              weeklyTarget: 0,
            })
          }
        >
          Add vehicle
        </button>
      </div>
      <div className="table-card">
        <table className="list">
          <thead>
            <tr>
              <th>Registration</th>
              <th>Company</th>
              <th className="num">Weekly target</th>
              <th>In the fleet from</th>
              <th className="num">Recurring items</th>
            </tr>
          </thead>
          <tbody>
            {visible.length ? (
              visible.map((vehicle) => (
                <tr key={vehicle.id}>
                  <td>
                    <button
                      className="row-btn"
                      onClick={() => setEditing(vehicle)}
                    >
                      {vehicle.registration}
                    </button>
                  </td>
                  <td>{vehicle.companyName}</td>
                  <td className="num">
                    KES {vehicle.weeklyTarget.toLocaleString()}
                    <small>
                      About KES{" "}
                      {Math.round(vehicle.weeklyTarget / 7).toLocaleString()} a
                      day
                    </small>
                  </td>
                  <td>{vehicle.joinedOn}</td>
                  <td className="num">-</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="empty-row" colSpan={5}>
                  No vehicles in this company yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function VehicleEditor({
  vehicle,
  companies,
  onCancel,
  onSaved,
}: {
  vehicle?: Vehicle;
  companies: Company[];
  onCancel: () => void;
  onSaved: (id?: string) => Promise<void>;
}) {
  const [form, setForm] = useState({
    companyId: vehicle?.companyId || companies[0]?.id || "",
    registration: vehicle?.registration || "",
    joinedOn: vehicle?.joinedOn || "",
    weeklyTarget: vehicle?.weeklyTarget ? String(vehicle.weeklyTarget) : "",
    reason: "",
  });
  const [period, setPeriod] = useState<"week" | "month">("week");
  const [report, setReport] = useState<{
    costs: number;
    savings: number;
    postings: { name: string; amount: number; date: string }[];
  } | null>(null);
  const [error, setError] = useState("");
  const isNew = !vehicle;
  async function save() {
    if (
      !form.companyId ||
      !form.registration.trim() ||
      !form.joinedOn ||
      Number(form.weeklyTarget) <= 0
    ) {
      setError("Enter a company, registration, fleet date, and weekly target.");
      return;
    }
    try {
      const result = await requestSetup<{ id: string }>(
        isNew ? "vehicles" : `vehicles/${vehicle.id}`,
        {
          method: isNew ? "POST" : "PUT",
          body: JSON.stringify({
            ...form,
            registration: form.registration.trim(),
            weeklyTarget: Number(form.weeklyTarget),
            reason:
              form.reason || (isNew ? "Added vehicle" : "Updated vehicle"),
          }),
        },
      );
      await onSaved(result.id);
    } catch (value) {
      setError((value as Error).message);
    }
  }
  async function loadReport(nextPeriod: "week" | "month") {
    if (!vehicle) return;
    setPeriod(nextPeriod);
    const from = nextPeriod === "week" ? "2026-09-21" : "2026-09-01";
    const through = nextPeriod === "week" ? "2026-09-27" : "2026-09-30";
    try {
      setReport(
        await requestSetup(
          `vehicles/${vehicle.id}/report?from=${from}&through=${through}`,
        ),
      );
    } catch (value) {
      setError((value as Error).message);
    }
  }
  useEffect(() => {
    if (vehicle) void loadReport("week");
  }, [vehicle]);
  return (
    <section className="form setup-detail">
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization administration</p>
          <h1>{isNew ? "Add vehicle" : vehicle.registration}</h1>
          <p className="muted">
            {isNew
              ? "It shows on reports and the dashboard straight away."
              : form.companyId &&
                companies.find((company) => company.id === form.companyId)
                  ?.name}
          </p>
        </div>
      </div>
      <SetupError message={error} />
      <article className="card">
        <header>
          <h2 className="card-title">Vehicle</h2>
        </header>
        <div className="grid2">
          <div className="f">
            <label htmlFor="vehicle-registration">Registration number</label>
            <input
              id="vehicle-registration"
              value={form.registration}
              disabled={!isNew}
              placeholder="KDA 482M"
              onChange={(event) =>
                setForm({
                  ...form,
                  registration: event.target.value.toUpperCase(),
                })
              }
            />
            <p className="hint">Kenyan format, for example KDA 482M.</p>
          </div>
          <div className="f">
            <label htmlFor="vehicle-company">PSV company</label>
            <select
              id="vehicle-company"
              value={form.companyId}
              onChange={(event) =>
                setForm({ ...form, companyId: event.target.value })
              }
            >
              <option value="">Choose a company</option>
              {companies.map((company) => (
                <option key={company.id} value={company.id}>
                  {company.name}
                </option>
              ))}
            </select>
          </div>
          <div className="f">
            <label htmlFor="vehicle-target">Weekly performance target</label>
            <input
              id="vehicle-target"
              type="number"
              min="1"
              value={form.weeklyTarget}
              onChange={(event) =>
                setForm({ ...form, weeklyTarget: event.target.value })
              }
            />
            <p className="hint">
              About KES{" "}
              {form.weeklyTarget
                ? Math.round(Number(form.weeklyTarget) / 7).toLocaleString()
                : "0"}{" "}
              a day.
            </p>
          </div>
          <div className="f">
            <label htmlFor="vehicle-joined">In the fleet from</label>
            <input
              id="vehicle-joined"
              type="date"
              value={form.joinedOn}
              onChange={(event) =>
                setForm({ ...form, joinedOn: event.target.value })
              }
            />
            <p className="hint">Missing revenue days start from this date.</p>
          </div>
        </div>
      </article>
      <div className="form-actions">
        <button className="btn-pill" onClick={() => void save()}>
          {isNew ? "Add vehicle" : "Save changes"}
        </button>
        <button className="btn-pill outline" onClick={onCancel}>
          Cancel
        </button>
      </div>
      {!isNew && (
        <article className="card">
          <header>
            <h2 className="card-title">Vehicle report</h2>
            <p className="card-sub">Recurring items post on their own dates.</p>
          </header>
          <div className="seg" role="group" aria-label="Report period">
            <button
              aria-pressed={period === "week"}
              onClick={() => void loadReport("week")}
            >
              This week
            </button>
            <button
              aria-pressed={period === "month"}
              onClick={() => void loadReport("month")}
            >
              This month
            </button>
          </div>
          {report && (
            <div className="report-grid">
              <div className="stat">
                <small>Running costs</small>
                <strong>KES {report.costs.toLocaleString()}</strong>
              </div>
              <div className="stat">
                <small>Savings set aside</small>
                <strong>KES {report.savings.toLocaleString()}</strong>
              </div>
            </div>
          )}
          {report?.postings.length ? (
            <ul className="card-list">
              {report.postings.map((posting) => (
                <li key={`${posting.name}-${posting.date}`}>
                  <span className="l">
                    <strong>{posting.name}</strong>
                    <small>{posting.date}</small>
                  </span>
                  <span className="r">
                    <strong>KES {posting.amount.toLocaleString()}</strong>
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            report && <p className="hint">Nothing posted in this period.</p>
          )}
        </article>
      )}
    </section>
  );
}

export function HistoryView() {
  const [rows, setRows] = useState<HistoryRow[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    void requestSetup<Page<HistoryRow>>("history")
      .then((page) => setRows(page.items))
      .catch((value) => setError((value as Error).message));
  }, []);
  return (
    <section>
      <p className="eyebrow">Organization administration</p>
      <h1>Change log</h1>
      <p className="muted">
        Every organizational setup change is recorded here.
      </p>
      <SetupError message={error} />
      <div className="table-card">
        <table className="list">
          <thead>
            <tr>
              <th>Section</th>
              <th>Reason</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {rows.length ? (
              rows.map((row) => (
                <tr key={row.version}>
                  <td>{row.section}</td>
                  <td>{row.reason}</td>
                  <td>{row.occurredAt}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="empty-row" colSpan={3}>
                  No setup changes yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function RecurringView() {
  type Item = {
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
    stoppedFrom?: string | null;
    allocations: { vehicleId: string; amount: number }[];
  };
  const [items, setItems] = useState<Item[]>([]);
  const [vehicles, setVehicles] = useState<Vehicle[]>([]);
  const [filter, setFilter] = useState("all");
  const [editing, setEditing] = useState<Item | null>(null);
  const [error, setError] = useState("");
  async function reload() {
    try {
      const [recurring, vehiclePage] = await Promise.all([
        requestSetup<Page<Item>>("recurring"),
        requestSetup<Page<Vehicle>>("vehicles"),
      ]);
      setItems(recurring.items);
      setVehicles(vehiclePage.items);
    } catch (value) {
      setError((value as Error).message);
    }
  }
  useEffect(() => {
    void reload();
  }, []);
  if (editing)
    return (
      <ReferenceRecurringEditor
        item={editing.id ? editing : undefined}
        vehicles={vehicles}
        onCancel={() => setEditing(null)}
        onSaved={async () => {
          setEditing(null);
          await reload();
        }}
      />
    );
  const visible = items.filter(
    (item) =>
      filter === "all" ||
      (filter === "cost" ? item.kind === 1 : item.kind === 2),
  );
  return (
    <section>
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization administration</p>
          <h1>Recurring costs and savings</h1>
          <p className="muted">
            Set once. Each posts to its vehicles on its own dates and shows in
            their reports.
          </p>
        </div>
      </div>
      <SetupError message={error} />
      <div className="toolbar recurring-toolbar">
        <div className="seg" role="group" aria-label="Show">
          <button
            aria-pressed={filter === "all"}
            onClick={() => setFilter("all")}
          >
            All
          </button>
          <button
            aria-pressed={filter === "cost"}
            onClick={() => setFilter("cost")}
          >
            Costs
          </button>
          <button
            aria-pressed={filter === "savings"}
            onClick={() => setFilter("savings")}
          >
            Savings
          </button>
        </div>
        <button
          className="btn-pill"
          onClick={() =>
            setEditing({
              id: "",
              name: "",
              kind: 1,
              category: 4,
              amount: 0,
              frequency: 3,
              day: 1,
              lastDay: false,
              start: "2026-09-25",
              allocations: [],
            })
          }
        >
          Add recurring cost or saving
        </button>
      </div>
      <div className="table-card">
        <table className="list">
          <thead>
            <tr>
              <th>Item</th>
              <th className="num">Amount each time</th>
              <th>How often</th>
              <th>Vehicles</th>
              <th>Period</th>
              <th>Next posting</th>
            </tr>
          </thead>
          <tbody>
            {visible.length ? (
              visible.map((item) => (
                <tr key={item.id}>
                  <td>
                    <button
                      className="row-btn"
                      onClick={() => setEditing(item)}
                    >
                      {item.name}
                    </button>
                    <small>{item.kind === 2 ? "Savings" : "Cost"}</small>
                  </td>
                  <td className="num">
                    KES {item.amount.toLocaleString()}
                    <small>
                      Across {item.allocations.length} vehicle
                      {item.allocations.length === 1 ? "" : "s"}
                    </small>
                  </td>
                  <td>
                    {item.frequency === 1
                      ? "Every day"
                      : item.frequency === 2
                        ? "Every week"
                        : "Every month"}
                  </td>
                  <td>{item.allocations.length}</td>
                  <td>
                    {item.start}
                    {item.end ? ` to ${item.end}` : <small>No end date</small>}
                  </td>
                  <td>
                    {item.stoppedFrom ? (
                      <span className="status status-off">Stopped</span>
                    ) : (
                      "Active"
                    )}
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td className="empty-row" colSpan={6}>
                  Nothing here yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function RecurringEditor({
  item,
  vehicles,
  onCancel,
  onSaved,
}: {
  item?: {
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
  vehicles: Vehicle[];
  onCancel: () => void;
  onSaved: () => Promise<void>;
}) {
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
  const [selected, setSelected] = useState<string[]>(
    item?.allocations.map((allocation) => allocation.vehicleId) || [],
  );
  const [error, setError] = useState("");
  const total = Number(amount) || 0;
  const share = selected.length ? total / selected.length : 0;
  async function save() {
    if (
      !name.trim() ||
      total <= 0 ||
      !start ||
      !selected.length ||
      (frequency === 2 && !day) ||
      (frequency === 3 && !lastDay && Number(day) > 28)
    ) {
      setError("Enter a name, amount, period, and at least one vehicle.");
      return;
    }
    try {
      const allocations = selected.map((vehicleId) => ({
        vehicleId,
        amount: share,
      }));
      const body = {
        name: name.trim(),
        kind,
        category: kind === 1 ? category : null,
        amount: total,
        frequency,
        day:
          frequency === 1
            ? null
            : frequency === 3 && lastDay
              ? null
              : Number(day),
        lastDay,
        start,
        end: end || null,
        allocations,
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
        body: JSON.stringify({
          confirmed: true,
          reason: "Stopped recurring item",
        }),
      });
      await onSaved();
    } catch (value) {
      setError((value as Error).message);
    }
  }
  return (
    <section className="form setup-detail">
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization administration</p>
          <h1>{isNew ? "Add recurring cost or saving" : name}</h1>
          <p className="muted">
            {isNew
              ? "It posts to the vehicles you choose on every due date in its period."
              : "Recurring item details and future postings."}
          </p>
        </div>
      </div>
      <SetupError message={error} />
      <article className="card">
        <header>
          <h2 className="card-title">What it is</h2>
        </header>
        <div className="grid2">
          <div className="f">
            <label htmlFor="recurring-name">Name</label>
            <input
              id="recurring-name"
              value={name}
              placeholder="For example Loan repayment"
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="f">
            <label htmlFor="recurring-kind">Type</label>
            <select
              id="recurring-kind"
              value={kind}
              onChange={(event) => setKind(Number(event.target.value))}
            >
              <option value="1">Cost</option>
              <option value="2">Savings</option>
            </select>
          </div>
          {kind === 1 && (
            <div className="f">
              <label htmlFor="recurring-category">Cost type</label>
              <select
                id="recurring-category"
                value={category}
                onChange={(event) => setCategory(Number(event.target.value))}
              >
                <option value="1">Running costs</option>
                <option value="2">Repairs and upkeep</option>
                <option value="3">Crew costs</option>
                <option value="4">Fixed commitments</option>
              </select>
            </div>
          )}
          <div className="f">
            <label htmlFor="recurring-amount">Amount each time</label>
            <input
              id="recurring-amount"
              type="number"
              min="1"
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
            <p className="hint">The total. Split it across vehicles below.</p>
          </div>
        </div>
      </article>
      <article className="card">
        <header>
          <h2 className="card-title">How often</h2>
        </header>
        <div className="grid2">
          <div className="f">
            <label htmlFor="recurring-frequency">Frequency</label>
            <select
              id="recurring-frequency"
              value={frequency}
              onChange={(event) => setFrequency(Number(event.target.value))}
            >
              <option value="1">Every day</option>
              <option value="2">Every week</option>
              <option value="3">Every month</option>
            </select>
          </div>
          {frequency !== 1 && (
            <div className="f">
              <label htmlFor="recurring-day">Day</label>
              <input
                id="recurring-day"
                type="number"
                min="1"
                max="28"
                value={day}
                disabled={frequency === 3 && lastDay}
                onChange={(event) => setDay(event.target.value)}
              />
            </div>
          )}
          <div className="f">
            <label htmlFor="recurring-start">Starts</label>
            <input
              id="recurring-start"
              type="date"
              value={start}
              onChange={(event) => setStart(event.target.value)}
            />
          </div>
          <div className="f">
            <label htmlFor="recurring-end">Ends</label>
            <input
              id="recurring-end"
              type="date"
              value={end}
              onChange={(event) => setEnd(event.target.value)}
            />
            <label className="check">
              <input
                type="checkbox"
                checked={lastDay}
                onChange={(event) => setLastDay(event.target.checked)}
              />{" "}
              Last day of month
            </label>
          </div>
        </div>
      </article>
      <article className="card">
        <header>
          <h2 className="card-title">Vehicles</h2>
          <p className="card-sub">
            Split the amount across one or more vehicles.
          </p>
        </header>
        <div className="vehicle-check-grid">
          {vehicles.map((vehicle) => (
            <label className="check" key={vehicle.id}>
              <input
                type="checkbox"
                checked={selected.includes(vehicle.id)}
                onChange={(event) =>
                  setSelected(
                    event.target.checked
                      ? [...selected, vehicle.id]
                      : selected.filter((id) => id !== vehicle.id),
                  )
                }
              />
              {vehicle.registration}
            </label>
          ))}
        </div>
        <p className="balance" role="status">
          Allocated KES {(share * selected.length).toLocaleString()} of KES{" "}
          {total.toLocaleString()}{" "}
          {selected.length && total
            ? "Balanced"
            : "Choose vehicles and enter an amount"}
        </p>
      </article>
      <div className="form-actions">
        <button className="btn-pill" onClick={() => void save()}>
          {isNew ? "Add" : "Save changes"}
        </button>
        <button className="btn-pill outline" onClick={onCancel}>
          {isNew ? "Cancel" : "Back"}
        </button>
        {item && (
          <button className="btn-pill danger" onClick={() => void stop()}>
            Stop from today
          </button>
        )}
      </div>
    </section>
  );
}
