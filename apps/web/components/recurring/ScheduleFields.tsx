import { MONTH_NAMES as monthNames, ordinal } from "@xcode/shared/dates";

import { useFormats } from "../../lib/formats";
import {
  RECURRING_FREQUENCY,
  RECURRING_FREQUENCY_OPTIONS,
} from "../recurringPresentation";
import { Choice, ChoiceField, Field, SelectInput, TextInput } from "../ui";
import type { RecurringFields } from "./fields";
import { dayOptions, weekdays } from "./schedule";
import type { SetField } from "./useRecurringFields";
import type { Errors } from "./validate";

type Props = {
  fields: RecurringFields;
  set: SetField;
  errors: Errors;
  disabled: boolean;
};

export function FrequencyFields({ fields, set, errors, disabled }: Props) {
  const { frequency, kind } = fields;
  return (
    <>
      <ChoiceField
        label="Runs"
        error={errors.frequency}
        hint={
          frequency === RECURRING_FREQUENCY.daily
            ? "Now every day, which is no longer offered."
            : kind === 2
              ? "Savings are set aside every week or every month."
              : undefined
        }
      >
        {RECURRING_FREQUENCY_OPTIONS.filter(
          (option) => kind === 1 || option.value !== RECURRING_FREQUENCY.yearly,
        ).map((option) => (
          <Choice
            key={option.value}
            type="radio"
            name="recurring-frequency"
            label={option.label}
            checked={frequency === option.value}
            disabled={disabled}
            onChange={() => set("frequency", option.value)}
          />
        ))}
      </ChoiceField>
      {frequency === RECURRING_FREQUENCY.weekly && (
        <Field id="recurring-weekday" label="On">
          <SelectInput
            value={fields.weekday}
            disabled={disabled}
            onChange={(event) => set("weekday", event.target.value)}
          >
            {weekdays.map((day) => (
              <option key={day.value} value={day.value}>
                {day.label}
              </option>
            ))}
          </SelectInput>
        </Field>
      )}
      {frequency === RECURRING_FREQUENCY.yearly && (
        <Field id="recurring-month" label="Month">
          <SelectInput
            value={fields.month}
            disabled={disabled}
            onChange={(event) => set("month", event.target.value)}
          >
            {monthNames.map((label, index) => (
              <option key={label} value={index + 1}>
                {label}
              </option>
            ))}
          </SelectInput>
        </Field>
      )}
      {(frequency === RECURRING_FREQUENCY.monthly ||
        frequency === RECURRING_FREQUENCY.yearly) && (
        <Field
          id="recurring-monthday"
          label="On"
          hint={
            frequency === RECURRING_FREQUENCY.monthly
              ? "For the 29th to the 31st, choose the last day so short months are covered."
              : "The day it falls due each year."
          }
        >
          <SelectInput
            value={fields.monthDay}
            disabled={disabled}
            onChange={(event) => set("monthDay", event.target.value)}
          >
            {dayOptions.map((value) => (
              <option key={value} value={value}>
                The {ordinal(value)}
              </option>
            ))}
            <option value="last">The last day</option>
          </SelectInput>
        </Field>
      )}
    </>
  );
}

type PeriodProps = Props & {
  start: string;
  earliestStart?: string;
  startLocked: boolean;
  periodIsValid: boolean;
};

export function PeriodFields({
  fields,
  set,
  errors,
  disabled,
  start,
  earliestStart,
  startLocked,
  periodIsValid,
}: PeriodProps) {
  const { formatDateOnly } = useFormats();
  return (
    <>
      <Field
        id="recurring-start"
        label="Starts"
        error={errors.start}
        hint={
          startLocked
            ? "Already running. Changes start today."
            : earliestStart
              ? `On or after ${formatDateOnly(earliestStart)}. A start before today also adds the earlier postings.`
              : "A start before today also adds the earlier postings."
        }
      >
        <TextInput
          type="date"
          value={start}
          min={startLocked ? undefined : earliestStart}
          disabled={disabled || startLocked}
          onChange={(event) => set("start", event.target.value)}
        />
      </Field>
      <div className="f">
        {!fields.noEnd && (
          <Field
            id="recurring-end"
            label="Ends"
            error={
              errors.end ??
              (!periodIsValid
                ? "End date must be on or after the start date."
                : undefined)
            }
          >
            <TextInput
              type="date"
              value={fields.end}
              min={start}
              disabled={disabled}
              onChange={(event) => set("end", event.target.value)}
            />
          </Field>
        )}
        <Choice
          label="No end date"
          checked={fields.noEnd}
          disabled={disabled}
          onChange={(event) => set("noEnd", event.target.checked)}
        />
      </div>
    </>
  );
}
