import type { ExpenseItemOption } from "../../lib/types";
import {
  Choice,
  ChoiceField,
  CurrencyInput,
  Field,
  SelectInput,
  TextInput,
} from "../ui";
import { NOTE_LIMIT, type RecurringFields } from "./fields";
import type { ItemPicker } from "./itemChoices";
import type { SetField } from "./useRecurringFields";
import type { Errors } from "./validate";

type Props = {
  fields: RecurringFields;
  set: SetField;
  setKind: (kind: number) => void;
  changeAmount: (value: string) => void;
  picker: ItemPicker;
  expenseItems?: ExpenseItemOption[];
  errors: Errors;
  disabled: boolean;
  canEdit: boolean;
};

const KINDS = [
  { value: 1, label: "Cost" },
  { value: 2, label: "Savings" },
];

function itemHint(picker: ItemPicker, expenseItemId: string) {
  const { picked, countedAs, noExpenseItem } = picker;
  if (picked)
    return `${picked.categoryName ? `${picked.categoryName}. ` : ""}${countedAs ? `Counts as ${countedAs}.` : ""}`;
  if (noExpenseItem && !expenseItemId)
    return `Saved before expense items${countedAs ? `, counting as ${countedAs}` : ""}. Choose the one it is for.`;
  return "Items come from Expense categories.";
}

function ExpenseItemSelect({
  fields,
  set,
  picker,
  expenseItems,
  errors,
  disabled,
  canEdit,
}: Pick<
  Props,
  | "fields"
  | "set"
  | "picker"
  | "expenseItems"
  | "errors"
  | "disabled"
  | "canEdit"
>) {
  return (
    <Field
      id="recurring-item"
      label="Item"
      error={errors.expenseItem}
      hint={itemHint(picker, fields.expenseItemId)}
    >
      <SelectInput
        value={fields.expenseItemId}
        disabled={disabled}
        onChange={(event) => set("expenseItemId", event.target.value)}
      >
        <option value="">
          {canEdit && expenseItems === undefined && !picker.picked
            ? "Loading expense items"
            : "Choose an item"}
        </option>
        {picker.groups.map((group) =>
          group[0].categoryName ? (
            <optgroup key={group[0].categoryId} label={group[0].categoryName}>
              {group.map((choice) => (
                <option key={choice.id} value={choice.id}>
                  {choice.name}
                </option>
              ))}
            </optgroup>
          ) : (
            group.map((choice) => (
              <option key={choice.id} value={choice.id}>
                {choice.off ? `${choice.name} (turned off)` : choice.name}
              </option>
            ))
          ),
        )}
      </SelectInput>
    </Field>
  );
}

export function KindAndItemFields(props: Props) {
  const { fields, set, setKind, changeAmount, errors, disabled } = props;
  return (
    <>
      <ChoiceField
        label="Type"
        hint={
          fields.kind === 2
            ? "Set aside each week or month, not counted as money out."
            : "Money out on the day it is paid."
        }
      >
        {KINDS.map((option) => (
          <Choice
            key={option.value}
            type="radio"
            name="recurring-kind"
            label={option.label}
            checked={fields.kind === option.value}
            disabled={disabled}
            onChange={() => setKind(option.value)}
          />
        ))}
      </ChoiceField>
      {fields.kind === 1 ? (
        <ExpenseItemSelect {...props} />
      ) : (
        <Field id="recurring-name" label="Name" error={errors.name}>
          <TextInput
            value={fields.name}
            placeholder="For example Owner savings"
            disabled={disabled}
            onChange={(event) => set("name", event.target.value)}
          />
        </Field>
      )}
      <Field
        id="recurring-note"
        label="Note"
        error={errors.note}
        hint={`Optional. Up to ${NOTE_LIMIT} characters.`}
      >
        <TextInput
          value={fields.note}
          maxLength={NOTE_LIMIT}
          placeholder="For example Zuri Genesis fleet"
          disabled={disabled}
          onChange={(event) => set("note", event.target.value)}
        />
      </Field>
      <Field
        id="recurring-amount"
        label="Amount each time"
        error={errors.amount}
        hint="The total. Split it across vehicles below."
      >
        <CurrencyInput
          min="1"
          value={fields.amount}
          disabled={disabled}
          onChange={(event) => changeAmount(event.target.value)}
        />
      </Field>
    </>
  );
}
