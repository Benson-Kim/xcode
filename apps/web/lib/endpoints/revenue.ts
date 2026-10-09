import type {
  RevenueDay,
  RevenueDaySaved,
  RevenueWeek,
  SaveRevenue,
  SaveRevenueDay,
} from "@xcode/shared/revenue";

import { apiRequest } from "../data";

const REVENUE_PATH = "setup/revenue";

export type RevenueWeekQuery = { weekStart: string; companyId: string };

export type RevenueWeekPageQuery = RevenueWeekQuery & {
  page: number;
  pageSize: number;
};

// A correction sends the version it was read at; a first capture sends null.
export type SaveDayRequest = SaveRevenue & { version: number | null };

export function revenueWeekPath({ weekStart, companyId }: RevenueWeekQuery) {
  const params = new URLSearchParams();
  if (weekStart) params.set("weekStart", weekStart);
  if (companyId) params.set("companyId", companyId);
  const encoded = params.toString();
  return `${REVENUE_PATH}${encoded ? `?${encoded}` : ""}`;
}

// The week the first response settled on, so a business date that moves meanwhile cannot mix two weeks.
export function revenueWeekPagePath({
  weekStart,
  companyId,
  page,
  pageSize,
}: RevenueWeekPageQuery) {
  const company = companyId
    ? `&companyId=${encodeURIComponent(companyId)}`
    : "";
  return `${REVENUE_PATH}?weekStart=${weekStart}${company}&page=${page}&pageSize=${pageSize}`;
}

// One vehicle's week: a capture day outside the grid's week, or a fresh look at the vehicle after a save.
export const vehicleWeekPath = (vehicleId: string, date: string) =>
  `${REVENUE_PATH}?weekStart=${date}&vehicleId=${vehicleId}`;

// Every vehicle active on one day, for the company chosen in the grid (all of them when none is).
export function fleetDayPath(date: string, companyId: string) {
  const params = new URLSearchParams({ date });
  if (companyId) params.set("companyId", companyId);
  return `${REVENUE_PATH}/day?${params}`;
}

export const revenueApi = {
  fleetDay: (date: string, companyId: string, signal?: AbortSignal) =>
    apiRequest<RevenueDay>(fleetDayPath(date, companyId), { signal }),
  saveFleetDay: (date: string, body: SaveRevenueDay) =>
    apiRequest<RevenueDaySaved>(`${REVENUE_PATH}/day/${date}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  vehicleWeek: (vehicleId: string, date: string) =>
    apiRequest<RevenueWeek>(vehicleWeekPath(vehicleId, date)),
  saveDay: (vehicleId: string, date: string, body: SaveDayRequest) =>
    apiRequest(`${REVENUE_PATH}/${vehicleId}/${date}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
};
