import { useRef, useState } from "react";

import { useResource } from "../../lib/data";
import { personPath } from "../../lib/endpoints/people";
import { useSession } from "../../lib/session-context";
import type {
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../../lib/types";
import { Banner, Button, Dialog } from "../ui";
import { type Pane, paneFor, removalRights } from "./model";
import { AccessPane } from "./PermissionsCard";
import { DetailsPane } from "./PersonCards";
import { PersonRail } from "./PersonRail";
import { type RemovalAction, RemovePane } from "./RemovePane";
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
  canBlock: boolean;
  canDelete: boolean;
  onRemoval: (person: Person, action: RemovalAction) => void;
  onClose: () => void;
  onSaved: (name: string, isNew: boolean, email: string) => void;
  onChanged: () => void;
};

// The person pop up (v2.32, v2.33): a side menu with a live summary of each section, and one pane at a time on
// the right. Details; Vehicles and dates; Sign in; Block or delete; Access, one card per module.
export function PersonEditor({
  person,
  roles,
  groups,
  scopeOptions,
  fullScope,
  today,
  canManage,
  canSignIn,
  canBlock,
  canDelete,
  onRemoval,
  onClose,
  onSaved,
  onChanged,
}: Props) {
  const { session } = useSession();
  const pf = usePersonForm(person, roles, groups);
  // The "Sign in" pane comes with the person's own record.
  const detail = useResource<Person>(person ? personPath(person.id) : null);
  const actions = usePersonActions({
    person,
    today,
    fullScope,
    onSaved,
    onChanged: () => {
      detail.reload();
      onChanged();
    },
  });
  const { errors } = actions;
  const [pane, setPane] = useState<Pane>("det");
  const paneRef = useRef<HTMLDivElement>(null);

  const self = Boolean(person && person.id === session?.userId);
  const ownerLock = person?.role === "Owner" && session?.role !== "Owner";
  const editable = canManage && !self && !ownerLock;
  const ready = Boolean(roles && groups);
  const removal = removalRights(person, session, {
    block: canBlock,
    remove: canDelete,
  });

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

  const signIn = detail.data?.signIn;

  return (
    <Dialog
      open
      size="xl"
      title={person ? `${person.firstName} ${person.lastName}` : "New person"}
      subtitle={person?.role ?? ""}
      busy={actions.busy}
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
        <PersonRail
          pane={pane}
          onShow={show}
          pf={pf}
          person={person}
          signIn={signIn}
          groups={groups}
          removable={removal.block || removal.remove}
        />
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
              onSendInvitation={() => void actions.sendInvitation()}
              onRemoveDevice={(deviceId) => void actions.removeDevice(deviceId)}
              onRemoveAll={() => void actions.removeAllDevices()}
            />
            {detail.error && <Banner>{detail.error}</Banner>}
          </div>
          {person && (removal.block || removal.remove) && (
            <div className="psecn" id="pp-rem" hidden={pane !== "rem"}>
              <RemovePane
                person={person}
                rights={removal}
                onAction={(action) => onRemoval(person, action)}
              />
            </div>
          )}
          <div className="psecn" id="pp-acc" hidden={pane !== "acc"}>
            <AccessPane
              groups={groups}
              ticks={pf.ticks}
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
