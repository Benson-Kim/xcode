import { useState } from "react";

import { ApiError } from "../../lib/data";
import { rolesApi } from "../../lib/endpoints/people";
import type { PermissionGroup, Role } from "../../lib/types";
import { Banner, Button, Dialog, Field, TextInput } from "../ui";
import { permissionTicks } from "./model";
import { AccessPane } from "./PermissionsCard";

export const ROLE_NAME_MAX = 100;

// An answer from an API without custom roles has no flag: every role was built in then.
export const isBuiltIn = (role: Role) => role.builtIn !== false;

// What is wrong with a role's name, if anything: it is needed, kept short, and unique (any case).
export function roleNameProblem(name: string, roles: Role[], id?: string) {
  const trimmed = name.trim();
  if (!trimmed) return "Enter the role's name.";
  if (trimmed.length > ROLE_NAME_MAX)
    return `Keep the name to ${ROLE_NAME_MAX} characters.`;
  if (
    roles.some(
      (other) =>
        other.id !== id && other.name.toLowerCase() === trimmed.toLowerCase(),
    )
  )
    return "Another role already has this name.";
  return "";
}

// Add or change a role: its name and the permissions a person given it starts with. Ticking a right ticks what it
// needs, as on a person. A built-in role, a role holding a permission the reader lacks (`outOfReach`), or anyone
// without access.manage, only reads it. A change based on an
// older version is refused (409): the page reloads the role and says so through `notice`. A name clash the screen
// could not see is a 400, shown as the server says it.
export function RoleDialog({
  role,
  groups,
  roles,
  editable,
  outOfReach = false,
  notice,
  onSaved,
  onConflict,
  onClose,
}: {
  role?: Role;
  groups?: PermissionGroup[];
  roles: Role[];
  editable: boolean;
  outOfReach?: boolean;
  notice: string;
  onSaved: (name: string, isNew: boolean) => void;
  onConflict: () => void;
  onClose: () => void;
}) {
  const [name, setName] = useState(role?.name ?? "");
  const [permissions, setPermissions] = useState(role?.permissions ?? []);
  const [nameError, setNameError] = useState("");
  const [ticksError, setTicksError] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const ticks = permissionTicks(groups, permissions, (next) => {
    setPermissions(next);
    setTicksError("");
  });

  async function save() {
    const invalidName = roleNameProblem(name, roles, role?.id);
    const invalidTicks = permissions.length ? "" : "Tick at least one.";
    setNameError(invalidName);
    setTicksError(invalidTicks);
    if (invalidName || invalidTicks) return;
    setBusy(true);
    setError("");
    try {
      await rolesApi.save(role, {
        name: name.trim(),
        permissions,
        version: role?.version,
      });
      onSaved(name.trim(), !role);
    } catch (value) {
      if (role && value instanceof ApiError && value.status === 409)
        onConflict();
      else setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      size="lg"
      title={role ? (editable ? "Edit role" : role.name) : "Add role"}
      subtitle={
        !role ? "" : editable ? role.name : isBuiltIn(role) ? "Built in" : ""
      }
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" onClick={onClose}>
            {editable ? "Cancel" : "Close"}
          </Button>
          {editable && (
            <Button
              type="submit"
              form="role-form"
              tone="ok"
              disabled={busy || !groups}
            >
              Save
            </Button>
          )}
        </>
      }
    >
      <form
        id="role-form"
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        {notice && <Banner>{notice}</Banner>}
        {role && !editable && isBuiltIn(role) && (
          <p className="muted">
            Built-in roles come with every organization and cannot be changed.
            Add a role to set your own defaults.
          </p>
        )}
        {outOfReach && (
          <p className="muted">
            You can change or delete a role only when you hold all of its
            permissions.
          </p>
        )}
        {editable && (
          <Field id="role-name" label="Name" error={nameError}>
            <TextInput
              autoFocus
              value={name}
              maxLength={ROLE_NAME_MAX}
              onChange={(event) => {
                setName(event.target.value);
                setNameError("");
              }}
            />
          </Field>
        )}
        <p className="muted">
          Someone given this role starts with these permissions. Each
          person&apos;s own can still be changed on them.
        </p>
        <AccessPane
          groups={groups}
          ticks={ticks}
          ready={Boolean(groups)}
          editable={editable}
          error={ticksError}
        />
        {error && <Banner>{error}</Banner>}
      </form>
    </Dialog>
  );
}
