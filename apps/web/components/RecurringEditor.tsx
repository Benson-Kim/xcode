"use client";

import { useAppearance } from "../lib/appearance";
import type { ExpenseItemOption } from "../lib/types";
import {
  deriveRecurring,
  recurringInput,
  recurringRequest,
} from "./recurring/derive";
import {
  PostingPreviewCard,
  RecurringActions,
  StopReasonCard,
} from "./recurring/RecurringCards";
import {
  RecurringNotices,
  recurringHeading,
} from "./recurring/RecurringNotices";
import { useAllocations } from "./recurring/useAllocations";
import { useRecurringActions } from "./recurring/useRecurringActions";
import { useRecurringFields } from "./recurring/useRecurringFields";
import { VehicleAllocationCard } from "./recurring/VehicleAllocationCard";
import { WhatAndWhenCard } from "./recurring/WhatAndWhenCard";
import type { RecurringItem, VehicleOption } from "./setup/shared";
import { Dialog, FormLayout } from "./ui";

type Props = {
  item?: RecurringItem;
  vehicles: VehicleOption[];
  // The active expense items a cost can pick (GET expense-items/options). Undefined while they load, or when only viewing.
  expenseItems?: ExpenseItemOption[];
  onCancel: () => void;
  onSaved: () => Promise<void> | void;
  canEdit?: boolean;
  preselectVehicle?: string;
  // The vehicle picker's list is still loading; the rest of the form is usable meanwhile.
  vehiclesLoading?: boolean;
  // Why a picker's list could not be loaded.
  loadError?: string;
};

export function RecurringEditor({
  item,
  vehicles,
  expenseItems,
  onCancel,
  onSaved,
  canEdit = true,
  preselectVehicle,
  vehiclesLoading = false,
  loadError,
}: Props) {
  const today = useAppearance().appearance?.businessDate;
  const { fields, set, setKind } = useRecurringFields(item);
  const alloc = useAllocations({
    item,
    vehicles,
    preselectVehicle,
    amount: fields.amount,
    setAmount: (value) => set("amount", value),
  });
  const derived = deriveRecurring({ item, fields, expenseItems, today });
  const { status } = derived;
  const actions = useRecurringActions({
    item,
    canEdit,
    locked: !canEdit || status.stopped,
    onSaved,
  });
  const disabled = !canEdit || status.stopped || actions.busy;

  const heading = recurringHeading(item);

  return (
    <Dialog
      open
      size="lg"
      title={heading.title}
      subtitle={heading.description}
      onClose={onCancel}
      footer={
        <RecurringActions
          isNew={!item}
          hasItem={Boolean(item)}
          canEdit={canEdit}
          stopped={status.stopped}
          futureStop={status.futureStop}
          confirmStop={actions.confirmStop}
          busy={actions.busy}
          onSave={() =>
            void actions.save(
              recurringInput(item, fields, derived, alloc),
              recurringRequest(fields, derived, alloc),
            )
          }
          onCancel={onCancel}
          onStop={() => void actions.stop()}
          onCancelStop={() => void actions.cancelStop()}
        />
      }
    >
      <FormLayout className="mt-0">
        <RecurringNotices
          item={item}
          status={status}
          today={today}
          canEdit={canEdit}
          errorCount={Object.keys(actions.errors).length}
          saveError={actions.saveError}
          loadError={loadError}
          legacyNeeds={derived.legacyNeeds}
        />
        <WhatAndWhenCard
          fields={fields}
          set={set}
          setKind={setKind}
          changeAmount={alloc.changeAmount}
          derived={derived}
          expenseItems={expenseItems}
          errors={actions.errors}
          disabled={disabled}
          canEdit={canEdit}
        />
        <VehicleAllocationCard
          vehicles={vehicles}
          vehiclesLoading={vehiclesLoading}
          disabled={disabled}
          alloc={alloc}
          error={actions.errors.allocations}
        />
        <PostingPreviewCard
          fields={fields}
          derived={derived}
          alloc={alloc}
          today={today}
        />
        {item && canEdit && !status.stopped && actions.confirmStop && (
          <StopReasonCard
            reason={actions.stopReason}
            error={actions.stopError}
            busy={actions.busy}
            onChange={actions.changeStopReason}
          />
        )}
      </FormLayout>
    </Dialog>
  );
}
