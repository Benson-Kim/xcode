import type { ExpenseItemOption } from "../../lib/types";
import { Card, CardHeader, Grid2 } from "../ui";
import type { Derived } from "./derive";
import type { RecurringFields } from "./fields";
import { KindAndItemFields } from "./KindAndItemFields";
import { FrequencyFields, PeriodFields } from "./ScheduleFields";
import type { SetField } from "./useRecurringFields";
import type { Errors } from "./validate";

type Props = {
  fields: RecurringFields;
  set: SetField;
  setKind: (kind: number) => void;
  changeAmount: (value: string) => void;
  derived: Derived;
  expenseItems?: ExpenseItemOption[];
  errors: Errors;
  disabled: boolean;
  canEdit: boolean;
};

export function WhatAndWhenCard(props: Props) {
  const { fields, set, errors, disabled, derived } = props;
  return (
    <Card density="form">
      <CardHeader title="What and how often" />
      <Grid2>
        <KindAndItemFields {...props} picker={derived.picker} />
        <FrequencyFields
          fields={fields}
          set={set}
          errors={errors}
          disabled={disabled}
        />
      </Grid2>
      <Grid2 narrow>
        <PeriodFields
          fields={fields}
          set={set}
          errors={errors}
          disabled={disabled}
          start={derived.start}
          earliestStart={derived.earliestStart}
          startLocked={derived.status.startLocked}
          periodIsValid={derived.periodOk}
        />
      </Grid2>
    </Card>
  );
}
