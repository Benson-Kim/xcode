import { Fragment } from "react";

import { plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import type { ScopeOptions } from "../../lib/types";
import { ListSkeleton } from "../ui";
import {
  backLimitText,
  earliestAllowed,
  type Errors,
  keptCounts,
  readBackLimit,
  scopeGroups,
} from "./model";
import type { PersonFormState } from "./usePersonForm";

// The "Vehicles and dates" pane (v2.32): the vehicles the person can see, and how far back they may change records.
export function VehiclesAndDatesPane({
  pf,
  scopeOptions,
  fullScope,
  editable,
  today,
  errors,
}: {
  pf: PersonFormState;
  scopeOptions?: ScopeOptions;
  // Whether the editor sees every vehicle: only then can "All vehicles" be given.
  fullScope: boolean;
  editable: boolean;
  today: string;
  errors: Errors;
}) {
  const { formatDateOnly } = useFormats();
  const { form, setField } = pf;
  const all = form.scopeMode === "all";
  const limit = readBackLimit(form);
  const earliest = today ? earliestAllowed(limit, today) : "";
  return (
    <>
      <div className="pblock">
        <div className="pbh">
          <b>Vehicles this person can see</b>
          {fullScope ? (
            <label className="mck">
              <input
                type="checkbox"
                id="pAll"
                checked={all}
                disabled={!editable}
                onChange={(event) => pf.setAllVehicles(event.target.checked)}
              />
              All vehicles
            </label>
          ) : all ? (
            <span className="hint">All vehicles</span>
          ) : null}
        </div>
        {(fullScope || !all) &&
          (!scopeOptions ? (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading the vehicles</span>
              <ListSkeleton rows={2} />
            </div>
          ) : (
            <VehicleTicks
              pf={pf}
              options={scopeOptions}
              editable={editable}
              hidden={all}
            />
          ))}
        {errors.scope && <div className="ferr">{errors.scope}</div>}
      </div>
      <div className="pblock">
        <div className="pbh">
          <b>How far back this person can change records</b>
          <span className="hint" id="pBackOut">
            {earliest ? `Today, from ${formatDateOnly(earliest)}` : "Any date"}
          </span>
        </div>
        <div className="mrow2">
          <div className="f">
            <label htmlFor="pBack">Limit</label>
            <select
              className="inp"
              id="pBack"
              value={form.backMode}
              disabled={!editable}
              onChange={(event) =>
                setField("backMode", event.target.value as typeof form.backMode)
              }
            >
              <option value="none">No rolling limit</option>
              <option value="days">A number of days back</option>
              <option value="months">A number of months back</option>
            </select>
          </div>
          {form.backMode !== "none" && (
            <div className="f">
              <label htmlFor="pBackN">
                {form.backMode === "months" ? "Months" : "Days"}
              </label>
              <input
                className="inp num"
                id="pBackN"
                inputMode="numeric"
                value={form.backCount}
                disabled={!editable}
                onChange={(event) =>
                  setField(
                    "backCount",
                    event.target.value.replace(/[^0-9]/g, ""),
                  )
                }
              />
            </div>
          )}
        </div>
        <div className="f">
          <div className="flabrow">
            <label className="mck">
              <input
                type="checkbox"
                id="pBackOn"
                checked={form.backFromOn}
                disabled={!editable}
                onChange={(event) =>
                  setField("backFromOn", event.target.checked)
                }
              />
              Never before a date
            </label>
          </div>
          {form.backFromOn && (
            <input
              className="inp"
              id="pBackDt"
              type="date"
              aria-label="Never before"
              max={today || undefined}
              value={form.backFrom}
              disabled={!editable}
              onChange={(event) => setField("backFrom", event.target.value)}
            />
          )}
        </div>
        <span className="sr-only">{backLimitText(limit, formatDateOnly)}</span>
        {errors.backLimit && <div className="ferr">{errors.backLimit}</div>}
      </div>
    </>
  );
}

function VehicleTicks({
  pf,
  options,
  editable,
  hidden,
}: {
  pf: PersonFormState;
  options: ScopeOptions;
  editable: boolean;
  hidden: boolean;
}) {
  const { form } = pf;
  const kept = keptCounts(form, options).vehicles;
  const ticked = (id: string) =>
    form.scopeMode === "vehicles" && form.vehicleIds.includes(id);
  return (
    <div
      role="group"
      aria-label="Vehicles this person can see"
      className="vgrid"
      id="pRegs"
      hidden={hidden}
    >
      {form.scopeMode === "companies" && (
        <span className="hint" style={{ gridColumn: "1 / -1" }}>
          Sees every vehicle of{" "}
          {plural(form.companyIds.length, "company", "companies")}. Tick
          vehicles to choose them one by one.
        </span>
      )}
      {scopeGroups(options).map((company) => (
        <Fragment key={company.id || "other"}>
          <span className="cogrp">{company.name}</span>
          <div className="checks">
            {company.vehicles.map((vehicle) => (
              <label key={vehicle.id} className="ck">
                <input
                  type="checkbox"
                  className="pv"
                  checked={ticked(vehicle.id)}
                  disabled={!editable}
                  onChange={(event) =>
                    pf.toggleVehicle(vehicle.id, event.target.checked)
                  }
                />
                {vehicle.registration}
              </label>
            ))}
          </div>
        </Fragment>
      ))}
      {!options.vehicles.length && (
        <span className="hint">No vehicle in your own access to choose.</span>
      )}
      {kept > 0 && (
        <span className="hint" style={{ gridColumn: "1 / -1" }}>
          {plural(kept, "vehicle", "vehicles")} outside your access or the fleet{" "}
          {kept === 1 ? "stays as it is" : "stay as they are"}.
        </span>
      )}
    </div>
  );
}
