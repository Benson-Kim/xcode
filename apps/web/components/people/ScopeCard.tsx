import { Fragment } from "react";

import { plural } from "@xcode/shared/format";

import type { ScopeOptions } from "../../lib/types";
import { Choice, ChoiceGroup, ErrorText, Hint, ListSkeleton } from "../ui";
import { keptCounts, type PersonForm, scopeGroups } from "./model";
import { FormSection, SectionLabel } from "./PersonCards";

type Props = {
  form: PersonForm;
  setField: <K extends keyof PersonForm>(key: K, value: PersonForm[K]) => void;
  toggleScope: (
    key: "companyIds" | "vehicleIds",
    id: string,
    checked: boolean,
  ) => void;
  scopeOptions?: ScopeOptions;
  selectedRole: string;
  editable: boolean;
  error?: string;
};

const SCOPE_MODES = [
  { value: "all", label: "All companies" },
  { value: "companies", label: "Chosen companies" },
  { value: "vehicles", label: "Chosen vehicles" },
];

const kept = (count: number, one: string, many: string, why: string) =>
  `Also ${plural(count, `${one} that is`, `${many} that are`)} not listed here: ${why}, or outside what you can see. ${count === 1 ? "It is" : "They are"} kept as ${count === 1 ? "it is" : "they are"}.`;

function CompanyChoices({
  form,
  toggleScope,
  options,
  editable,
}: Pick<Props, "form" | "toggleScope" | "editable"> & {
  options: ScopeOptions;
}) {
  const keptCompanies = keptCounts(form, options).companies;
  return (
    <ChoiceGroup label="Companies they can see">
      {options.companies.map((company) => (
        <Choice
          key={company.id}
          label={company.name}
          checked={form.companyIds.includes(company.id)}
          disabled={!editable}
          onChange={(event) =>
            toggleScope("companyIds", company.id, event.target.checked)
          }
        />
      ))}
      {!options.companies.length && (
        <Hint>There are no companies in your own scope to choose from.</Hint>
      )}
      {keptCompanies > 0 && (
        <Hint>{kept(keptCompanies, "company", "companies", "archived")}</Hint>
      )}
    </ChoiceGroup>
  );
}

function VehicleChoices({
  form,
  toggleScope,
  options,
  editable,
}: Pick<Props, "form" | "toggleScope" | "editable"> & {
  options: ScopeOptions;
}) {
  const keptVehicles = keptCounts(form, options).vehicles;
  return (
    <div role="group" aria-label="Vehicles they can see" className="vgrid">
      {scopeGroups(options).map((company) => (
        <Fragment key={company.id || "other"}>
          <span className="cogrp">{company.name}</span>
          <ChoiceGroup className="checks">
            {company.vehicles.map((vehicle) => (
              <Choice
                key={vehicle.id}
                label={vehicle.registration}
                checked={form.vehicleIds.includes(vehicle.id)}
                disabled={!editable}
                onChange={(event) =>
                  toggleScope("vehicleIds", vehicle.id, event.target.checked)
                }
              />
            ))}
          </ChoiceGroup>
        </Fragment>
      ))}
      {!options.vehicles.length && (
        <Hint>There are no vehicles in your own scope to choose from.</Hint>
      )}
      {keptVehicles > 0 && (
        <Hint>
          {kept(keptVehicles, "vehicle", "vehicles", "out of the fleet")}
        </Hint>
      )}
    </div>
  );
}

export function ScopeCard(props: Props) {
  const { form, setField, scopeOptions, selectedRole, editable } = props;
  return (
    <FormSection>
      <SectionLabel
        title="What they can see"
        description="Every number, list and report is limited to this."
      />
      <ChoiceGroup role="radiogroup" label="What they can see">
        {SCOPE_MODES.map((option) => (
          <Choice
            key={option.value}
            type="radio"
            name="person-scope"
            label={option.label}
            checked={form.scopeMode === option.value}
            disabled={!editable || selectedRole === "Owner"}
            onChange={() => setField("scopeMode", option.value)}
          />
        ))}
      </ChoiceGroup>
      {form.scopeMode !== "all" && !scopeOptions ? (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading what they can see</span>
          <ListSkeleton rows={2} />
        </div>
      ) : form.scopeMode === "companies" && scopeOptions ? (
        <CompanyChoices {...props} options={scopeOptions} />
      ) : form.scopeMode === "vehicles" && scopeOptions ? (
        <VehicleChoices {...props} options={scopeOptions} />
      ) : (
        <Hint>
          {selectedRole === "Owner"
            ? "The owner always sees every company."
            : "Includes any company added later."}
        </Hint>
      )}
      {props.error && <ErrorText>{props.error}</ErrorText>}
    </FormSection>
  );
}
