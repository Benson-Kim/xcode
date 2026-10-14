import { apiRequest } from "../data";

export const VEHICLES_PATH = "setup/vehicles";

export const vehiclePath = (id: string) => `${VEHICLES_PATH}/${id}`;
export const vehicleTargetsPath = (id: string) => `${vehiclePath(id)}/targets`;

export type CreateVehicleRequest = {
  registration: string;
  companyId: string;
  joinedOn: string;
  fleetNumber: string;
  dayTargets: number[];
  initialInvestment: number | null;
};

export type UpdateVehicleRequest = {
  companyId: string;
  joinedOn: string;
  fleetNumber: string;
  initialInvestment: number | null;
};

export type SaveTargetRequest = { startsOn: string; days: number[] };

export const vehiclesApi = {
  create: (body: CreateVehicleRequest) =>
    apiRequest<{ id: string }>(VEHICLES_PATH, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  update: (id: string, body: UpdateVehicleRequest) =>
    apiRequest<{ id: string }>(vehiclePath(id), {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  saveTarget: (id: string, body: SaveTargetRequest) =>
    apiRequest<{ id: string }>(vehicleTargetsPath(id), {
      method: "POST",
      body: JSON.stringify(body),
    }),
  removeTarget: (targetId: string) =>
    apiRequest<{ id: string }>(`setup/vehicle-targets/${targetId}/remove`, {
      method: "POST",
    }),
};
