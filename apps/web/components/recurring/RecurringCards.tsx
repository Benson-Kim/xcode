import { plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import {
  recurringMonthlyEstimate,
  recurringNextPostings,
} from "../recurringPresentation";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  Field,
  Hint,
  TextInput,
} from "../ui";
import type { Derived } from "./derive";
import type { RecurringFields } from "./fields";
import type { Allocations } from "./useAllocations";

type PreviewProps = {
  fields: RecurringFields;
  derived: Derived;
  alloc: Allocations;
  today?: string;
};

export function PostingPreviewCard({
  fields,
  derived,
  alloc,
  today,
}: PreviewProps) {
  const { kes, formatDateOnly } = useFormats();
  const { postingTotal } = alloc;
  const postingCount = alloc.postingIds.length;
  const { countedAs } = derived.picker;
  const dates =
    today && postingTotal > 0 && postingCount && derived.periodOk
      ? recurringNextPostings(derived.schedule, today, 5)
      : [];
  return (
    <Card density="form">
      <CardHeader title="What will post" description="Worked out for you" />
      {dates.length ? (
        <>
          <ol className="m-0 list-decimal pl-5">
            {dates.map((date) => (
              <li key={date} className="py-0.5 tabular-nums">
                {formatDateOnly(date)}: {kes(postingTotal)} across{" "}
                {plural(postingCount, "vehicle", "vehicles")}
              </li>
            ))}
          </ol>
          <Hint>
            About{" "}
            {kes(recurringMonthlyEstimate(postingTotal, fields.frequency))} a
            month.{" "}
            {fields.kind === 2
              ? "Shown as savings in each vehicle report."
              : countedAs
                ? `Counted under ${countedAs} in each vehicle report.`
                : "Counted as money out in each vehicle report."}
          </Hint>
        </>
      ) : (
        <Hint>
          {!alloc.total || !alloc.selected.length
            ? "Enter the amount and choose vehicles to see the postings."
            : !derived.periodOk
              ? "The end date is before the start date."
              : !today
                ? "The postings show once the business date has loaded."
                : "No postings from today in this period."}
        </Hint>
      )}
    </Card>
  );
}

export function StopReasonCard({
  reason,
  error,
  busy,
  onChange,
}: {
  reason: string;
  error: string;
  busy: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Card density="form">
      <CardHeader
        title="Stop from today"
        description="A short reason is required and is kept in the change log."
      />
      <Field id="recurring-stop-reason" label="Reason for stopping">
        <TextInput
          autoFocus
          maxLength={500}
          placeholder="For example, the loan is paid off"
          value={reason}
          disabled={busy}
          aria-invalid={Boolean(error) || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      </Field>
      {error && <Banner>{error}</Banner>}
    </Card>
  );
}

type ActionsProps = {
  isNew: boolean;
  hasItem: boolean;
  canEdit: boolean;
  stopped: boolean;
  futureStop: string | null;
  confirmStop: boolean;
  busy: boolean;
  onSave: () => void;
  onCancel: () => void;
  onStop: () => void;
  onCancelStop: () => void;
};

export function RecurringActions(props: ActionsProps) {
  const { busy, canEdit, stopped, futureStop } = props;
  const editable = canEdit && !stopped;
  return (
    <>
      {props.hasItem && editable && futureStop && (
        <Button
          tone="outline"
          className="mr-auto"
          disabled={busy}
          onClick={props.onCancelStop}
        >
          Cancel stop
        </Button>
      )}
      {props.hasItem && editable && !futureStop && (
        <Button
          tone="warn"
          className="mr-auto"
          disabled={busy}
          onClick={props.onStop}
        >
          {props.confirmStop
            ? "Tap again to stop from today"
            : "Stop from today"}
        </Button>
      )}
      <Button tone="outline" disabled={busy} onClick={props.onCancel}>
        {editable ? "Cancel" : "Back"}
      </Button>
      {editable && (
        <Button
          tone="ok"
          disabled={busy}
          aria-busy={busy || undefined}
          onClick={props.onSave}
        >
          {busy ? "Saving..." : props.isNew ? "Add" : "Save changes"}
        </Button>
      )}
    </>
  );
}
