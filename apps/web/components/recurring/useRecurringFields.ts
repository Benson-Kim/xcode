import { useState } from "react";

import { RECURRING_FREQUENCY } from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";
import { initialFields, type RecurringFields } from "./fields";

export type SetField = <K extends keyof RecurringFields>(
  key: K,
  value: RecurringFields[K],
) => void;

// A new item may start as a saving (kind 2) when opened from the Savings tab.
export function useRecurringFields(item?: RecurringItem, startKind?: number) {
  const [fields, setFields] = useState(() => {
    const base = initialFields(item);
    if (item || !startKind || startKind === base.kind) return base;
    return {
      ...base,
      kind: startKind,
      frequency:
        startKind === 2 && base.frequency === RECURRING_FREQUENCY.yearly
          ? RECURRING_FREQUENCY.monthly
          : base.frequency,
    };
  });

  function set<K extends keyof RecurringFields>(
    key: K,
    value: RecurringFields[K],
  ) {
    setFields((current) => ({ ...current, [key]: value }));
  }

  function setKind(kind: number) {
    setFields((current) => ({
      ...current,
      kind,
      // Savings are set aside every week or every month
      frequency:
        kind === 2 && current.frequency === RECURRING_FREQUENCY.yearly
          ? RECURRING_FREQUENCY.monthly
          : current.frequency,
    }));
  }

  return { fields, set, setKind };
}
