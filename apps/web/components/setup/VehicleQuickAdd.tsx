"use client";

import { useAppearance } from "../../lib/appearance";
import { useResource, useStreamedList } from "../../lib/data";
import { useSession } from "../../lib/session-context";
import type { Company, Vehicle } from "./shared";
import {
  companyChoices,
  VehicleEditor,
  type CompanyChoice,
} from "./VehiclesPage";

export { useVehicleAddRight } from "./VehiclesPage";

// The new vehicle pop up, opened from another form's vehicle list with what was typed there. Saving hands the new
// vehicle back; cancelling closes it and leaves that form as it was. An entry dated before the business date has
// the vehicle join on the entry's date, so the entry can use it.
export function VehicleQuickAdd({
  registration,
  date,
  onCreated,
  onClose,
}: {
  registration: string;
  date?: string;
  onCreated: (vehicle: Vehicle) => void;
  onClose: () => void;
}) {
  const { can } = useSession();
  const { appearance } = useAppearance();
  const businessDate = appearance?.businessDate;
  const canSeeCompanies = can("companies.manage") || can("companies.view");
  const companyList = useStreamedList<Company>(
    canSeeCompanies ? "setup/companies" : null,
  );
  const companyOptions = useResource<CompanyChoice[]>(
    canSeeCompanies ? null : "setup/vehicles/company-options",
  );
  return (
    <VehicleEditor
      defaultCompany=""
      companies={companyChoices([], companyList.items, companyOptions.data)}
      today={businessDate}
      joinsOn={date && businessDate && date < businessDate ? date : undefined}
      initialRegistration={registration.toUpperCase()}
      onClose={onClose}
      onCompaniesChanged={() => {
        companyList.reload();
        companyOptions.reload();
      }}
      onSaved={onCreated}
    />
  );
}
