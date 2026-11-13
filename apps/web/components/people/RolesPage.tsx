"use client";

import { useState } from "react";

import { plural } from "@xcode/shared/format";

import { useResource } from "../../lib/data";
import { CATALOG_PATH, ROLES_PATH, rolesApi } from "../../lib/endpoints/people";
import { useSession } from "../../lib/session-context";
import type { PermissionGroup, Role } from "../../lib/types";
import { useDeleteRecord } from "../setup/DeleteRecordDialog";
import {
  Banner,
  Button,
  DataTable,
  PageHeader,
  RowAction,
  Td,
  Tr,
  useToast,
} from "../ui";
import { isBuiltIn, RoleDialog } from "./RoleDialog";

const CONFLICT =
  "Someone else changed this role while you had it open. It has been reloaded with their change: make yours again.";

// Built-in roles first, then the organization's own, each by name.
const ordered = (roles: Role[]) =>
  [...roles].sort(
    (left, right) =>
      Number(isBuiltIn(right)) - Number(isBuiltIn(left)) ||
      left.name.localeCompare(right.name),
  );

// Roles: the built-in ones, read only, and the organization's own, each a name and the permissions a person given
// it starts with. Anyone who can see people sees them; adding needs access.manage, and changing or deleting one
// also needs every permission it holds.
export function RolesPage() {
  const { session, can } = useSession();
  const canManage = can("access.manage");
  const mine = new Set(session?.permissions ?? []);
  const withinReach = (role: Role) =>
    role.permissions.every((key) => mine.has(key));
  const changeable = (role: Role) =>
    canManage && !isBuiltIn(role) && withinReach(role);
  const toast = useToast();
  const roles = useResource<Role[]>(ROLES_PATH);
  const catalog = useResource<PermissionGroup[]>(CATALOG_PATH);
  const [open, setOpen] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const deletion = useDeleteRecord(roles.reload);
  const list = ordered(roles.data ?? []);
  const total = catalog.data?.reduce(
    (sum, group) => sum + group.items.length,
    0,
  );
  const role = list.find((candidate) => candidate.id === open);
  const showing = open === "new" || Boolean(role);

  const close = () => {
    setOpen(null);
    setNotice("");
  };

  return (
    <>
      <PageHeader
        title="Roles"
        actions={
          canManage && (
            <Button tone="primary" onClick={() => setOpen("new")}>
              Add role
            </Button>
          )
        }
      />
      {(roles.error || catalog.error) && (
        <Banner>{roles.error || catalog.error}</Banner>
      )}
      {notice && !showing && <Banner>{notice}</Banner>}
      <DataTable
        columns={[
          { label: "Role" },
          { label: "Permissions" },
          { label: "Actions", numeric: true },
        ]}
        loading={roles.loading}
        loadingLabel="Loading roles"
        isEmpty={!list.length}
        failed={Boolean(roles.error)}
        emptyMessage="No roles yet."
      >
        {list.map((row) => (
          <Tr key={row.id}>
            <Td label="Role" className="item">
              {row.name}{" "}
              {isBuiltIn(row) && <span className="chip mute">Built in</span>}
            </Td>
            <Td label="Permissions">
              {total
                ? `${row.permissions.length} of ${total}`
                : plural(row.permissions.length, "permission", "permissions")}
            </Td>
            <Td numeric>
              <RoleActions
                role={row}
                editable={changeable(row)}
                onOpen={() => {
                  setNotice("");
                  setOpen(row.id);
                }}
                onDelete={() =>
                  deletion.ask({
                    noun: "role",
                    name: row.name,
                    remove: () => rolesApi.remove(row.id),
                    rule: "It can be deleted only while nobody holds it.",
                  })
                }
              />
            </Td>
          </Tr>
        ))}
      </DataTable>
      {showing && (
        <RoleDialog
          key={role ? `${role.id}:${role.version ?? ""}` : "new"}
          role={role}
          groups={catalog.data}
          roles={list}
          editable={!role ? canManage : changeable(role)}
          outOfReach={Boolean(
            role && canManage && !isBuiltIn(role) && !withinReach(role),
          )}
          notice={notice}
          onSaved={(name, isNew) => {
            toast(isNew ? `${name} added.` : `${name} saved.`);
            close();
            roles.reload();
          }}
          onConflict={() => {
            setNotice(CONFLICT);
            roles.reload();
          }}
          onClose={close}
        />
      )}
      {deletion.dialog}
    </>
  );
}

function RoleActions({
  role,
  editable,
  onOpen,
  onDelete,
}: {
  role: Role;
  editable: boolean;
  onOpen: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="tacts">
      <RowAction
        aria-label={`${editable ? "Edit" : "View"} ${role.name}`}
        onClick={onOpen}
      >
        {editable ? "Edit" : "View"}
      </RowAction>
      {editable && (
        <RowAction
          tone="bad"
          aria-label={`Delete ${role.name}`}
          onClick={onDelete}
        >
          Delete
        </RowAction>
      )}
    </div>
  );
}
