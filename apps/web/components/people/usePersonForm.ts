import { useState } from "react";

import { useSession } from "../../lib/session-context";
import type {
  Permission,
  PermissionGroup,
  Person,
  Role,
} from "../../lib/types";
import {
  APPROVALS,
  assignableRoles,
  changesFromRole,
  initialForm,
  type PersonForm,
  roleDefaults,
  withNeeds,
  withoutDependents,
} from "./model";

export function usePersonForm(
  person: Person | undefined,
  roles: Role[] | undefined,
  groups: PermissionGroup[] | undefined,
) {
  const { session } = useSession();
  const [form, setForm] = useState(() => initialForm(person));
  const [permissionNote, setPermissionNote] = useState("");

  const all = (groups ?? []).flatMap((group) => group.items);
  const label = (key: string) =>
    all.find((item) => item.key === key)?.label ?? key;
  const assignable = assignableRoles(roles, person, session);
  const selectedRole =
    assignable.find((role) => role.name === form.role)?.name ??
    assignable[0]?.name ??
    (roles ? "" : form.role);
  const defaults = roleDefaults(roles, selectedRole);
  const permissions = form.permissions ?? defaults;

  function setField<K extends keyof PersonForm>(key: K, value: PersonForm[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function togglePermission(item: Permission, checked: boolean) {
    const next = checked
      ? withNeeds(permissions, item.key, all)
      : withoutDependents(permissions, item.key, all);
    const added = next.filter(
      (key) => !permissions.includes(key) && key !== item.key,
    );
    const removed = permissions.filter(
      (key) => !next.includes(key) && key !== item.key,
    );
    setPermissionNote(
      added.length
        ? `Also ticked, because it is needed: ${added.map(label).join(", ")}.`
        : removed.length
          ? `Also unticked, because it needs this: ${removed.map(label).join(", ")}.`
          : "",
    );
    setField("permissions", next);
  }

  function resetPermissions() {
    setPermissionNote("");
    setField("permissions", null);
  }

  function changeRole(role: string) {
    setPermissionNote("");
    setForm((current) => ({
      ...current,
      role,
      permissions: null,
      scopeMode: role === "Owner" ? "all" : current.scopeMode,
    }));
  }

  function toggleScope(
    key: "companyIds" | "vehicleIds",
    id: string,
    checked: boolean,
  ) {
    setForm((current) => ({
      ...current,
      [key]: checked
        ? [...current[key], id]
        : current[key].filter((value) => value !== id),
    }));
  }

  return {
    form,
    setField,
    label,
    assignable,
    selectedRole,
    defaults,
    permissions,
    changes: changesFromRole(permissions, defaults),
    needsLimit: permissions.some((key) => APPROVALS.includes(key)),
    permissionNote,
    togglePermission,
    resetPermissions,
    changeRole,
    toggleScope,
  };
}

export type PersonFormState = ReturnType<typeof usePersonForm>;
