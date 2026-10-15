"use client";

import { useId, useState, type FormEvent } from "react";

import {
  PETTY_CASH_NOTE_LIMIT,
  PETTY_CASH_UNITS_ERROR,
  parsePettyCashAmount,
  parsePettyCashUnits,
  pettyCashTotal,
  type PettyCashEntry,
  type PettyCashFloat,
  type PettyCashHolder,
  type PettyCashKind,
  type PettyCashOptions,
  type PettyCashPermissions,
  type PettyCashSaved,
  type PettyCashVehicleOption,
  type SavePettyCashEntry,
} from "@xcode/shared/pettyCash";
import { vehicleLabel } from "@xcode/shared/revenue";

import { useResource } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import {
  Banner,
  Button,
  ErrorSummary,
  Field,
  SearchSelect,
  TextInput,
} from "../ui";
import { AmountInput } from "./AmountInput";
import { DateStep } from "./DateStep";
import { DialogFooter, FormDialog } from "./DialogFooter";
import { HolderField } from "./HolderField";
import { itemOptions } from "./itemOptions";
import {
  ENTRIES_PATH,
  entryPath,
  newEntryId,
  optionsPath,
  sendJson,
} from "./request";
import { useDialogAction } from "./useDialogAction";

export type EntryDialogState = { kind: PettyCashKind; entry?: PettyCashEntry };

type Errors = Partial<
  Record<"units" | "amount" | "vehicle" | "item" | "holder", string>
>;

type VehicleChoice = PettyCashVehicleOption;

const TITLES: Record<PettyCashKind, string> = {
  expense: "Record spending",
  credit: "Credit note",
  cash: "Issue cash",
};

// Whose float a new expense goes on: the manager on screen for someone who may add for another manager and see every
// float, otherwise their own float. With neither, the form asks.
function spendingHolder(
  permissions: PettyCashPermissions,
  holderId: string,
): { holder: string; asks: boolean } {
  if (permissions.canSpendOther && permissions.canViewAll && holderId)
    return { holder: holderId, asks: false };
  if (permissions.holderId)
    return { holder: permissions.holderId, asks: false };
  return { holder: "", asks: true };
}

export function EntryDialog({
  state,
  date,
  businessDate,
  permissions,
  holderId,
  holders,
  floats,
  onSaved,
  onConflict,
  onClose,
}: {
  state: EntryDialogState | null;
  date: string;
  businessDate: string;
  permissions: PettyCashPermissions;
  // The manager the list is filtered to, offered first when cash is given.
  holderId: string;
  // The managers the page already knows, which name the float a new expense goes on.
  holders?: PettyCashHolder[];
  // The floats the page already knows, which say what cash a manager holds.
  floats?: PettyCashFloat[];
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const title = !state
    ? ""
    : state.entry
      ? "Edit spending"
      : TITLES[state.kind];
  const short = state !== null && state.kind !== "expense";
  const onFloat =
    state?.kind !== "expense"
      ? undefined
      : state.entry
        ? state.entry.holderId
        : spendingHolder(permissions, holderId).holder;
  const subtitle = onFloat
    ? (state?.entry?.holderName ??
      holders?.find((candidate) => candidate.id === onFloat)?.name)
    : undefined;
  return (
    <FormDialog
      open={Boolean(state)}
      title={title}
      size={short ? "sm" : undefined}
      subtitle={subtitle}
      onClose={onClose}
    >
      {state && (
        <EntryForm
          kind={state.kind}
          entry={state.entry}
          viewedDate={date}
          businessDate={businessDate}
          permissions={permissions}
          holderId={holderId}
          floats={floats}
          onSaved={onSaved}
          onConflict={onConflict}
          onClose={onClose}
        />
      )}
    </FormDialog>
  );
}

function EntryForm({
  kind,
  entry,
  viewedDate,
  businessDate,
  permissions,
  holderId,
  floats,
  onSaved,
  onConflict,
  onClose,
}: {
  kind: PettyCashKind;
  entry?: PettyCashEntry;
  viewedDate: string;
  businessDate: string;
  permissions: PettyCashPermissions;
  holderId: string;
  floats?: PettyCashFloat[];
  onSaved: (message: string) => void;
  onConflict: (message: string) => void;
  onClose: () => void;
}) {
  const formats = useFormats();
  const earliest = permissions.earliestDate ?? null;
  const spend =
    kind === "expense" ? spendingHolder(permissions, holderId) : null;
  // One id per opened form: a save that is repeated after a lost answer creates nothing twice.
  const [newId] = useState(newEntryId);
  const [date, setDate] = useState(
    entry?.date ?? (earliest && viewedDate < earliest ? earliest : viewedDate),
  );
  const [units, setUnits] = useState(String(entry?.units ?? 1));
  const [amount, setAmount] = useState(entry ? String(entry.unitAmount) : "");
  const [vehicleId, setVehicleId] = useState(entry?.vehicleId ?? "");
  const [itemId, setItemId] = useState(entry?.expenseItemId ?? "");
  const [reason, setReason] = useState("");
  const [holder, setHolder] = useState(
    entry?.holderId ??
      spend?.holder ??
      (kind === "cash" ? holderId : holderId || (permissions.holderId ?? "")),
  );
  const [errors, setErrors] = useState<Errors>({});
  const { saving, error, run } = useDialogAction(onConflict);
  const formId = useId();

  // The choices follow the date on the form; while the next ones load, the last ones stay.
  const options = useResource<PettyCashOptions>(optionsPath(date));
  const [held, setHeld] = useState<PettyCashOptions | undefined>(options.data);
  if (options.data && options.data !== held) setHeld(options.data);
  const choices = options.data ?? held;

  const vehicles: VehicleChoice[] = choices?.vehicles ?? [];
  const vehicleChoices: VehicleChoice[] =
    entry?.vehicleId &&
    !vehicles.some((vehicle) => vehicle.id === entry.vehicleId)
      ? [
          ...vehicles,
          {
            id: entry.vehicleId,
            registration: entry.registration ?? "",
            companyId: "",
            companyName: "",
            active: false,
          },
        ]
      : vehicles;
  const items = choices?.items ?? [];
  const itemChoices =
    entry?.expenseItemId &&
    !items.some((item) => item.id === entry.expenseItemId)
      ? [
          ...items,
          {
            id: entry.expenseItemId,
            name: entry.expenseItemName ?? "",
            categoryName: "Other",
            categoryId: "",
            bucket: entry.bucket ?? 2,
          },
        ]
      : items;
  const holderList: PettyCashHolder[] = choices?.holders ?? [];
  const holderChoices =
    entry && !holderList.some((candidate) => candidate.id === entry.holderId)
      ? [
          ...holderList,
          { id: entry.holderId, name: entry.holderName, active: false },
        ]
      : holderList;

  const parsed = parsePettyCashAmount(amount);
  const count = parsePettyCashUnits(units);
  const total =
    kind === "expense" && parsed.ok && count !== null
      ? pettyCashTotal(count, parsed.amount)
      : null;
  const pickHolder = kind !== "expense" || Boolean(spend?.asks && !entry);

  function submit(event: FormEvent) {
    event.preventDefault();
    const found: Errors = {};
    if (!parsed.ok) found.amount = parsed.error;
    if (kind === "expense") {
      if (count === null) found.units = PETTY_CASH_UNITS_ERROR;
      if (!vehicleId) found.vehicle = "Choose the vehicle.";
      if (!itemId) found.item = "Choose what it was for.";
    }
    if (pickHolder && !holder) found.holder = "Choose the manager.";
    setErrors(found);
    if (!parsed.ok || Object.keys(found).length) return;

    const body: SavePettyCashEntry = {
      ...(entry ? { version: entry.version } : { id: newId }),
      kind,
      date,
      unitAmount: parsed.amount,
      note: kind === "credit" ? reason.trim() || null : (entry?.note ?? null),
    };
    if (kind === "expense")
      Object.assign(body, { vehicleId, expenseItemId: itemId, units: count });
    if (kind !== "expense" || (!entry && holder !== permissions.holderId))
      body.holderId = holder;

    void run(async () => {
      await (entry
        ? sendJson<PettyCashSaved>("PUT", entryPath(entry.id), body)
        : sendJson<PettyCashSaved>("POST", ENTRIES_PATH, body));
      if (entry) return onSaved("Saved. It waits for approval.");
      if (kind === "cash") {
        const name =
          holderChoices.find((candidate) => candidate.id === holder)?.name ??
          "the manager";
        return onSaved(
          parsed.amount < 0
            ? `${formats.kes(-parsed.amount)} taken back from ${name}.`
            : `${formats.kes(parsed.amount)} given to ${name}.`,
        );
      }
      if (kind === "credit")
        return onSaved(
          `Credit note of ${formats.kes(parsed.amount)} recorded.`,
        );
      const registration =
        vehicleChoices.find((vehicle) => vehicle.id === vehicleId)
          ?.registration ?? "the vehicle";
      onSaved(
        `${formats.kes(total ?? parsed.amount)} recorded on ${registration}. It waits for approval.`,
      );
    });
  }

  return (
    <form
      id={formId}
      noValidate
      onSubmit={submit}
      className="flex flex-col gap-3.5"
    >
      {options.error && !choices && <Banner>{options.error}</Banner>}
      <DateStep
        date={date}
        earliest={earliest}
        latest={businessDate}
        onChange={setDate}
      />
      {pickHolder && (
        <HolderField
          holders={holderChoices}
          value={holder}
          error={errors.holder}
          floats={floats}
          showBalance={kind !== "expense"}
          autoFocus={!holder}
          onChange={setHolder}
        />
      )}
      {kind === "expense" ? (
        <>
          <Field id="pc-vehicle" label="Vehicle" error={errors.vehicle}>
            <SearchSelect
              options={vehicleChoices.map((vehicle) => ({
                value: vehicle.id,
                label: vehicleLabel(vehicle),
              }))}
              value={vehicleId}
              placeholder="Choose vehicle"
              onChange={setVehicleId}
            />
          </Field>
          <Field id="pc-item" label="Item" error={errors.item}>
            <SearchSelect
              options={itemOptions(itemChoices)}
              value={itemId}
              placeholder="Search item"
              onChange={setItemId}
            />
          </Field>
          <div className="mrow">
            <Field id="pc-units" label="Qty" error={errors.units}>
              <TextInput
                inputMode="decimal"
                autoComplete="off"
                className="num"
                value={units}
                onChange={(event) => setUnits(event.target.value)}
              />
            </Field>
            <Field
              id="pc-amount"
              label={`Unit cost, ${formats.currencyCode()}`}
              error={errors.amount}
            >
              <AmountInput
                autoFocus={!pickHolder || Boolean(holder)}
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
              />
            </Field>
          </div>
          <div className="mtot">
            <span>Total amount</span>
            <b className="num">{formats.kes(total ?? 0)}</b>
          </div>
        </>
      ) : (
        <>
          <Field
            id="pc-amount"
            label={`Amount, ${formats.currencyCode()}`}
            error={errors.amount}
          >
            <AmountInput
              autoFocus={Boolean(holder)}
              value={amount}
              onChange={(event) => setAmount(event.target.value)}
            />
          </Field>
          {kind === "credit" && (
            <Field id="pc-note" label="Reason">
              <TextInput
                maxLength={PETTY_CASH_NOTE_LIMIT}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            </Field>
          )}
        </>
      )}
      <ErrorSummary count={Object.keys(errors).length} />
      {error && <Banner>{error}</Banner>}
      <DialogFooter>
        <Button tone="outline" onClick={onClose}>
          Cancel
        </Button>
        <Button type="submit" form={formId} tone="ok" disabled={saving}>
          {kind === "cash" ? "Issue cash" : "Save"}
        </Button>
      </DialogFooter>
    </form>
  );
}
