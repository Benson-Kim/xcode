import { apiRequest } from "../data";

export const RECURRING_PATH = "setup/recurring";

export const recurringPath = (id: string) => `${RECURRING_PATH}/${id}`;

export type SaveRecurringRequest = {
  name: string;
  kind: number;
  amount: number;
  frequency: number;
  day: number | null;
  lastDay: boolean;
  start: string;
  end: string | null;
  allocations: { vehicleId: string; amount: number }[];
  expenseItemId: string | null;
  note: string | null;
  month: number | null;
};

export const recurringApi = {
  save: (item: { id: string } | undefined, body: SaveRecurringRequest) =>
    apiRequest(item ? recurringPath(item.id) : RECURRING_PATH, {
      method: item ? "PUT" : "POST",
      body: JSON.stringify(body),
    }),
  stop: (id: string, reason: string) =>
    apiRequest(`${recurringPath(id)}/stop`, {
      method: "POST",
      body: JSON.stringify({ confirmed: true, reason: reason.trim() }),
    }),
  restore: (id: string) =>
    apiRequest(`${recurringPath(id)}/restore`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
};
