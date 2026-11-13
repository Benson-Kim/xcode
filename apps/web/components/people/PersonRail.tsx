import { plural } from "@xcode/shared/format";
import { RIGHTS } from "@xcode/shared/permissions";

import { useFormats } from "../../lib/formats";
import type { PermissionGroup, Person, PersonSignIn } from "../../lib/types";
import {
  backLimitText,
  type Pane,
  personStatus,
  readBackLimit,
  statusChip,
} from "./model";
import type { PersonFormState } from "./usePersonForm";

type Note = { text: string; className?: string; two?: boolean };

// The person pop up's side menu: one entry a pane with a live summary of it, and under Access one entry a module.
// "Block or delete" sits with the person's own sections, before the long module list.
export function PersonRail({
  pane,
  onShow,
  pf,
  person,
  signIn,
  groups,
  removable,
}: {
  pane: Pane;
  onShow: (pane: Pane, group?: number) => void;
  pf: PersonFormState;
  person?: Person;
  signIn?: PersonSignIn;
  groups?: PermissionGroup[];
  removable: boolean;
}) {
  const { formatDateOnly } = useFormats();
  const { form } = pf;
  const limitWords = backLimitText(readBackLimit(form), formatDateOnly);
  const vehiclesWords =
    form.scopeMode === "all"
      ? "All vehicles"
      : form.scopeMode === "companies"
        ? plural(form.companyIds.length, "company", "companies")
        : plural(form.vehicleIds.length, "vehicle", "vehicles");
  const status = person && statusChip(signIn?.status ?? personStatus(person));
  const signWords = status
    ? `${status.label}${
        signIn?.devices.length
          ? ` · ${plural(signIn.devices.length, "device", "devices")}`
          : ""
      }`
    : "Not signed in yet";
  const held = pf.permissions;
  const total = groups
    ? groups.reduce((sum, group) => sum + group.items.length, 0)
    : RIGHTS.length;

  const entry = (target: Pane, label: string, note?: Note, group?: number) => (
    <button
      key={`${target}-${group ?? ""}`}
      type="button"
      className={
        group !== undefined ? "pnav sub" : note?.two ? "pnav two" : "pnav"
      }
      aria-current={pane === target && group === undefined ? "true" : undefined}
      onClick={() => onShow(target, group)}
    >
      <span>{label}</span>
      {note && <small className={note.className}>{note.text}</small>}
    </button>
  );

  return (
    <nav className="prail" aria-label="Sections">
      {entry("det", "Details")}
      {entry("lim", "Vehicles and dates", {
        text: `${vehiclesWords} · ${limitWords}`,
        two: true,
      })}
      {entry("sig", "Sign in", { text: signWords, two: true })}
      {person &&
        removable &&
        entry("rem", "Block or delete", {
          text: statusChip(personStatus(person)).label,
        })}
      {entry("acc", "Access", { text: `${held.length} of ${total}` })}
      {groups?.map((group, index) => {
        const count = group.items.filter((item) =>
          held.includes(item.key),
        ).length;
        return entry(
          "acc",
          group.name,
          {
            text:
              count === group.items.length
                ? "All"
                : count
                  ? `${count} of ${group.items.length}`
                  : "Off",
            className: count === group.items.length ? "on" : count ? "" : "off",
          },
          index,
        );
      })}
    </nav>
  );
}
