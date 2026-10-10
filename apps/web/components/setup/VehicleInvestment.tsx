"use client";

import { useState } from "react";

import { plural } from "@xcode/shared/format";

import { apiRequest, useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import type { VehicleInvestment } from "../../lib/types";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  CardNote,
  CurrencyInput,
  DataTable,
  Dialog,
  Field,
  Hint,
  ListSkeleton,
  ProgressBar,
  RowAction,
  Spacer,
  Stat,
  StatGrid,
  Td,
  TextInput,
  Toolbar,
  Tr,
  useToast,
} from "../ui";

// An entry being added or changed. A null date means "not chosen yet": it follows the business date.
type Draft = { description: string; amount: string; date: string | null };

const blank: Draft = { description: "", amount: "", date: null };

// The API takes any date up to the business date.
function problem(draft: Draft, date: string, today?: string) {
  if (!draft.description.trim()) return "Say what it was.";
  if (!(Number(draft.amount) > 0)) return "Enter the amount in KES.";
  if (!date) return "Enter the date.";
  if (today && date > today)
    return "The date cannot be after the business date.";
  return "";
}

// The Investment tab on a vehicle: what went into it, and how much of that has come back (its net contribution since
// it joined, worked out by the server). Investment is never counted as money out. Seeing it needs invest.view;
// adding, changing and removing entries need invest.manage.
export function VehicleInvestmentTab({
  vehicle,
  today,
}: {
  vehicle: { id: string; registration: string; joinedOn?: string };
  today?: string;
}) {
  const { can } = useSession();
  const { formatDateOnly, formatDateRange, kes, money } = useFormats();
  const canManage = can("invest.manage");
  const toast = useToast();
  const investment = useResource<VehicleInvestment>(
    `setup/vehicles/${vehicle.id}/investment`,
  );
  const [adding, setAdding] = useState<Draft | null>(null);
  const [addError, setAddError] = useState("");
  const [editing, setEditing] = useState<(Draft & { id: string }) | null>(null);
  const [confirmRemove, setConfirmRemove] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const data = investment.data;
  const entries = [...(data?.entries ?? [])].sort((left, right) =>
    left.date.localeCompare(right.date),
  );

  async function send(path: string, method: string, draft?: Draft) {
    setBusy(true);
    try {
      await apiRequest(path, {
        method,
        ...(draft
          ? {
              body: JSON.stringify({
                date: draft.date ?? today,
                description: draft.description.trim(),
                amount: Number(draft.amount),
              }),
            }
          : {}),
      });
      investment.reload();
      return "";
    } catch (value) {
      return (value as Error).message;
    } finally {
      setBusy(false);
    }
  }

  async function add() {
    if (!adding) return;
    const invalid = problem(adding, adding.date ?? today ?? "", today);
    if (invalid) return setAddError(invalid);
    const failed = await send(
      `setup/vehicles/${vehicle.id}/investment`,
      "POST",
      adding,
    );
    if (failed) return setAddError(failed);
    toast(`${adding.description.trim()} added.`);
    setAdding(null);
  }

  async function saveEdit() {
    if (!editing) return;
    const invalid = problem(editing, editing.date ?? "", today);
    if (invalid) return setError(invalid);
    const failed = await send(`setup/investment/${editing.id}`, "PUT", editing);
    setError(failed);
    if (failed) return;
    toast("Saved.");
    setEditing(null);
  }

  async function remove(id: string) {
    if (confirmRemove !== id) return setConfirmRemove(id);
    const failed = await send(`setup/investment/${id}`, "DELETE");
    setConfirmRemove(null);
    setError(failed);
    if (!failed) toast("Removed.");
  }

  const paidOff = data?.percentPaidOff ?? null;
  return (
    <div className="stack">
      <Card>
        <CardHeader
          title={`What went into ${vehicle.registration}`}
          description="Money put in before and around buying it. It is not counted as money out."
        />
        {investment.loading ? (
          <div role="status" aria-busy="true">
            <span className="sr-only">Loading the investment</span>
            <ListSkeleton rows={2} />
          </div>
        ) : !data ? (
          <Hint>{investment.error}</Hint>
        ) : (
          <>
            <StatGrid>
              <Stat label="Invested" value={kes(data.totalInvested)} />
              <Stat
                label="Back so far"
                value={data.returned === null ? "—" : money(data.returned)}
                tone={
                  data.returned !== null && data.returned < 0
                    ? "bad"
                    : undefined
                }
              />
              <Stat
                label="Paid back"
                value={paidOff === null ? "—" : `${Math.round(paidOff)}%`}
              />
            </StatGrid>
            {paidOff !== null && <ProgressBar value={paidOff} />}
            <CardNote>
              {data.returned === null
                ? "Back so far and paid back show once they can be worked out from the revenue records."
                : `Back so far counts net contribution from the records kept${
                    vehicle.joinedOn && today && vehicle.joinedOn <= today
                      ? `, ${formatDateRange(vehicle.joinedOn, today)}`
                      : ""
                  }.`}
            </CardNote>
          </>
        )}
      </Card>
      {error && <Banner>{error}</Banner>}
      <Toolbar>
        {data && <Hint>{plural(entries.length, "entry", "entries")}</Hint>}
        <Spacer />
        {canManage && (
          <Button
            tone="ok"
            onClick={() => {
              setAddError("");
              setAdding({ ...blank });
            }}
          >
            Add investment
          </Button>
        )}
      </Toolbar>
      <DataTable
        columns={[
          { label: "Date" },
          { label: "What it was" },
          { label: "Amount", numeric: true },
          ...(canManage ? [{ label: "Actions", numeric: true }] : []),
        ]}
        loading={investment.loading}
        loadingLabel="Loading investment entries"
        isEmpty={!entries.length}
        failed={Boolean(investment.error)}
        emptyMessage="Nothing recorded yet."
      >
        {entries.map((entry) =>
          editing?.id === entry.id ? (
            <Tr key={entry.id}>
              <Td label="Date">
                <TextInput
                  type="date"
                  aria-label="Date"
                  density="compact"
                  max={today}
                  value={editing.date ?? ""}
                  onChange={(event) =>
                    setEditing({ ...editing, date: event.target.value })
                  }
                />
              </Td>
              <Td label="What it was">
                <TextInput
                  aria-label="What it was"
                  density="compact"
                  value={editing.description}
                  onChange={(event) =>
                    setEditing({ ...editing, description: event.target.value })
                  }
                  onKeyDown={(event) => {
                    if (event.key === "Enter") void saveEdit();
                    if (event.key === "Escape") setEditing(null);
                  }}
                />
              </Td>
              <Td label="Amount" numeric>
                <CurrencyInput
                  aria-label="Amount"
                  density="compact"
                  value={editing.amount}
                  onChange={(event) =>
                    setEditing({ ...editing, amount: event.target.value })
                  }
                />
              </Td>
              <Td numeric>
                <div className="tacts">
                  <RowAction
                    tone="ok"
                    disabled={busy}
                    onClick={() => void saveEdit()}
                  >
                    Save
                  </RowAction>
                  <RowAction
                    onClick={() => {
                      setEditing(null);
                      setError("");
                    }}
                  >
                    Cancel
                  </RowAction>
                </div>
              </Td>
            </Tr>
          ) : (
            <Tr key={entry.id}>
              <Td label="Date" className="nw">
                {formatDateOnly(entry.date)}
              </Td>
              <Td label="What it was" className="item">
                {entry.description}
              </Td>
              <Td label="Amount" numeric>
                {kes(entry.amount)}
              </Td>
              {canManage && (
                <Td numeric>
                  <div className="tacts">
                    <RowAction
                      disabled={busy}
                      aria-label={`Edit ${entry.description}`}
                      onClick={() => {
                        setError("");
                        setConfirmRemove(null);
                        setEditing({
                          id: entry.id,
                          description: entry.description,
                          amount: String(entry.amount),
                          date: entry.date,
                        });
                      }}
                    >
                      Edit
                    </RowAction>
                    <RowAction
                      tone="bad"
                      disabled={busy}
                      aria-label={`${confirmRemove === entry.id ? "Tap again to remove" : "Remove"} ${entry.description}`}
                      onClick={() => void remove(entry.id)}
                    >
                      {confirmRemove === entry.id
                        ? "Tap again to remove"
                        : "Remove"}
                    </RowAction>
                  </div>
                </Td>
              )}
            </Tr>
          ),
        )}
      </DataTable>
      <Dialog
        open={Boolean(adding)}
        title="Add investment"
        subtitle={vehicle.registration}
        onClose={() => setAdding(null)}
        footer={
          <>
            <Button tone="outline" onClick={() => setAdding(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="investment-add-form"
              tone="ok"
              disabled={busy}
            >
              Add
            </Button>
          </>
        }
      >
        {adding && (
          <form
            id="investment-add-form"
            className="contents"
            onSubmit={(event) => {
              event.preventDefault();
              void add();
            }}
          >
            <Field id="investment-description" label="What it was">
              <TextInput
                autoFocus
                value={adding.description}
                placeholder="For example Deposit on the unit"
                onChange={(event) =>
                  setAdding({ ...adding, description: event.target.value })
                }
              />
            </Field>
            <Field id="investment-amount" label="Amount">
              <CurrencyInput
                value={adding.amount}
                onChange={(event) =>
                  setAdding({ ...adding, amount: event.target.value })
                }
              />
            </Field>
            <Field id="investment-date" label="Date">
              <TextInput
                type="date"
                max={today}
                value={adding.date ?? today ?? ""}
                onChange={(event) =>
                  setAdding({ ...adding, date: event.target.value })
                }
              />
            </Field>
            {addError && <Banner>{addError}</Banner>}
          </form>
        )}
      </Dialog>
    </div>
  );
}
