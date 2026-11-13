import { useState } from "react";

import { useSession } from "../../lib/session-context";
import type { PermissionGroup, Person, Role } from "../../lib/types";
import {
  APPROVALS,
  assignableRoles,
  FLOAT_RIGHT,
  initialForm,
  type PersonForm,
  permissionTicks,
  roleDefaults,
} from "./model";

export function usePersonForm(
  person: Person | undefined,
  roles: Role[] | undefined,
  groups: PermissionGroup[] | undefined,
) {
  const { session } = useSession();
  const [form, setForm] = useState(() => initialForm(person));

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

  const ticks = permissionTicks(groups, permissions, (next) =>
    setField("permissions", next),
  );

  function changeRole(role: string) {
    setForm((current) => ({
      ...current,
      role,
      permissions: null,
      scopeMode: role === "Owner" ? "all" : current.scopeMode,
    }));
  }

  // Ticking a vehicle puts the person on chosen vehicles; "All vehicles" takes them off any list.
  function toggleVehicle(id: string, checked: boolean) {
    setForm((current) => {
      const chosen = current.scopeMode === "vehicles" ? current.vehicleIds : [];
      return {
        ...current,
        scopeMode: "vehicles",
        companyIds: [],
        vehicleIds: checked
          ? [...chosen, id]
          : chosen.filter((value) => value !== id),
      };
    });
  }

  function setAllVehicles(all: boolean) {
    setForm((current) => ({
      ...current,
      scopeMode: all ? "all" : "vehicles",
      vehicleIds: all ? [] : current.vehicleIds,
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
    needsLimit: permissions.some((key) => APPROVALS.includes(key)),
    holdsFloat: permissions.includes(FLOAT_RIGHT),
    setFloat: (holds: boolean) => ticks.setPermission(FLOAT_RIGHT, holds),
    ticks,
    changeRole,
    toggleVehicle,
    setAllVehicles,
  };
}

export type PersonFormState = ReturnType<typeof usePersonForm>;
