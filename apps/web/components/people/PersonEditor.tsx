import { useRef, useState } from "react";

import { plural } from "@xcode/shared/format";
import { RIGHTS } from "@xcode/shared/permissions";

import { useResource } from "../../lib/data";
import { personPath } from "../../lib/endpoints/people";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
import type {
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../../lib/types";
import { Banner, Button, Dialog } from "../ui";
import {
  backLimitText,
  type Pane,
  paneFor,
  personStatus,
  readBackLimit,
  STATUS_CHIPS,
} from "./model";
import { AccessPane } from "./PermissionsCard";
import { DetailsPane } from "./PersonCards";
import { VehiclesAndDatesPane } from "./ScopeCard";
import { SignInPane } from "./SignInPane";
import { usePersonActions } from "./usePersonActions";
import { usePersonForm } from "./usePersonForm";

type Props = {
  person?: Person;
  // Each arrives on its own request; until then its section shows placeholders.
  roles?: Role[];
  groups?: PermissionGroup[];
  scopeOptions?: ScopeOptions;
  fullScope: boolean;
  today: string;
  canManage: boolean;
  canSignIn: boolean;
  onClose: () => void;
  onSaved: (name: string, isNew: boolean) => void;
  onChanged: () => void;
};

// The person pop up (v2.32, v2.33): a side menu with a live summary of each section, and one pane at a time on
// the right. Details; Vehicles and dates; Sign in; Access, one card per module.
export function PersonEditor({
  person,
  roles,
  groups,
  scopeOptions,
  fullScope,
  today,
  canManage,
  canSignIn,
  onClose,
  onSaved,
  onChanged,
}: Props) {
  const { session } = useSession();
  const { formatDateOnly } = useFormats();
  const pf = usePersonForm(person, roles, groups);
  // The "Sign in" pane comes with the person's own record.
  const detail = useResource<Person>(person ? personPath(person.id) : null);
  const actions = usePersonActions({
    person,
    today,
    onSaved,
    onChanged: () => {
      detail.reload();
      onChanged();
    },
  });
  const { errors } = actions;
  const { form } = pf;
  const [pane, setPane] = useState<Pane>("det");
  const paneRef = useRef<HTMLDivElement>(null);

  const self = Boolean(person && person.id === session?.userId);
  const ownerLock = person?.role === "Owner" && session?.role !== "Owner";
  const editable = canManage && !self && !ownerLock;
  const ready = Boolean(roles && groups);

  // A save error opens the pane that holds the problem.
  const [seenErrors, setSeenErrors] = useState(errors);
  if (errors !== seenErrors) {
    setSeenErrors(errors);
    const target = paneFor(errors);
    if (target) setPane(target);
  }

  function show(next: Pane, group?: number) {
    setPane(next);
    if (group !== undefined)
      setTimeout(
        () =>
          document
            .getElementById(`pg-${group}`)
            ?.scrollIntoView({ block: "start" }),
        0,
      );
    else paneRef.current?.scrollTo?.(0, 0);
  }

  const limitWords = backLimitText(readBackLimit(form), formatDateOnly);
  const vehiclesWords =
    form.scopeMode === "all"
      ? "All vehicles"
      : form.scopeMode === "companies"
        ? plural(form.companyIds.length, "company", "companies")
        : plural(form.vehicleIds.length, "vehicle", "vehicles");
  const signIn = detail.data?.signIn;
  const signWords = person
    ? `${STATUS_CHIPS[signIn?.status ?? personStatus(person)].label}${
        signIn?.devices.length
          ? ` · ${plural(signIn.devices.length, "device", "devices")}`
          : ""
      }`
    : "Not signed in yet";
  const held = pf.permissions;
  const total = groups
    ? groups.reduce((sum, group) => sum + group.items.length, 0)
    : RIGHTS.length;

  const navButton = (
    target: Pane,
    label: string,
    small?: { text: string; className?: string; two?: boolean },
    group?: number,
  ) => (
    <button
      key={`${target}-${group ?? ""}`}
      type="button"
      className={
        group !== undefined ? "pnav sub" : small?.two ? "pnav two" : "pnav"
      }
      aria-current={pane === target && group === undefined ? "true" : undefined}
      onClick={() => show(target, group)}
    >
      <span>{label}</span>
      {small && <small className={small.className}>{small.text}</small>}
    </button>
  );

  return (
    <Dialog
      open
      size="xl"
      title={person ? `${person.firstName} ${person.lastName}` : "New person"}
      subtitle={person?.role ?? ""}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" onClick={onClose}>
            {editable ? "Cancel" : "Close"}
          </Button>
          {editable && (
            <Button
              tone="ok"
              disabled={actions.busy || !ready}
              onClick={() => void actions.save(pf, Boolean(roles))}
            >
              Save
            </Button>
          )}
        </>
      }
    >
      <div className="pwrap">
        <nav className="prail" aria-label="Sections">
          {navButton("det", "Details")}
          {navButton("lim", "Vehicles and dates", {
            text: `${vehiclesWords} · ${limitWords}`,
            two: true,
          })}
          {navButton("sig", "Sign in", { text: signWords, two: true })}
          {navButton("acc", "Access", {
            text: `${held.length} of ${total}`,
          })}
          {groups?.map((group, index) => {
            const count = group.items.filter((item) =>
              held.includes(item.key),
            ).length;
            return navButton(
              "acc",
              group.name,
              {
                text:
                  count === group.items.length
                    ? "All"
                    : count
                      ? `${count} of ${group.items.length}`
                      : "Off",
                className:
                  count === group.items.length ? "on" : count ? "" : "off",
              },
              index,
            );
          })}
        </nav>
        <div className="ppane" id="ppane" ref={paneRef}>
          {actions.saveError && <Banner>{actions.saveError}</Banner>}
          {!canManage && person ? (
            <Banner>You can view people but not change them.</Banner>
          ) : self ? (
            <Banner>
              This is you. Someone else who manages people changes your details
              and access.
            </Banner>
          ) : ownerLock ? (
            <Banner>Only the owner can change the owner&apos;s access.</Banner>
          ) : null}
          <div className="psecn" id="pp-det" hidden={pane !== "det"}>
            <DetailsPane
              pf={pf}
              roles={roles}
              errors={errors}
              editable={editable}
              limitEditable={editable}
            />
          </div>
          <div className="psecn" id="pp-lim" hidden={pane !== "lim"}>
            <VehiclesAndDatesPane
              pf={pf}
              scopeOptions={scopeOptions}
              fullScope={fullScope}
              editable={editable}
              today={today}
              errors={errors}
            />
          </div>
          <div className="psecn" id="pp-sig" hidden={pane !== "sig"}>
            <SignInPane
              person={person}
              signIn={signIn}
              loading={detail.loading}
              canAct={canSignIn && !self}
              busy={actions.busy}
              onPinReset={() => void actions.pinReset()}
              onRemoveDevice={(deviceId) => void actions.removeDevice(deviceId)}
              onRemoveAll={() => void actions.removeAllDevices()}
            />
            {detail.error && <Banner>{detail.error}</Banner>}
          </div>
          <div className="psecn" id="pp-acc" hidden={pane !== "acc"}>
            <AccessPane
              groups={groups}
              pf={pf}
              ready={ready}
              editable={editable}
              error={errors.permissions}
            />
          </div>
        </div>
      </div>
    </Dialog>
  );
}
