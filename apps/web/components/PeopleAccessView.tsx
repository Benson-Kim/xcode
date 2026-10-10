"use client";

import { useState } from "react";

import { streamError, useResource } from "../lib/data";
import {
  CATALOG_PATH,
  PEOPLE_PATH,
  RECENT_CHANGES_PATH,
  ROLES_PATH,
  SCOPE_PATH,
} from "../lib/endpoints/people";
import { useSession } from "../lib/session-context";
import type {
  ChangeLogPage,
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../lib/types";
import { PeopleList, type PeopleFilters } from "./people/PeopleList";
import { PersonEditor } from "./people/PersonEditor";
import { RecentChanges } from "./people/RecentChanges";
import type { HistoryRow } from "./setup/shared";
import { Banner, Button, ListPager, PageHeader } from "./ui";
import { usePagedList } from "./usePagedList";

export function PeopleAccessView({
  canManageAccess = false,
}: {
  canManageAccess?: boolean;
}) {
  const { can } = useSession();
  const canManage = can("people.manage") || canManageAccess;
  const roles = useResource<Role[]>(ROLES_PATH);
  const catalog = useResource<PermissionGroup[]>(CATALOG_PATH);
  const scope = useResource<ScopeOptions>(canManage ? SCOPE_PATH : null);
  const recent = useResource<ChangeLogPage<HistoryRow>>(
    can("audit.view") ? RECENT_CHANGES_PATH : null,
  );
  const [editing, setEditing] = useState<Person | "new" | null>(null);
  // Filters at the top of the list, as in the design: role, and where they are with signing in.
  const [filters, setFilters] = useState<PeopleFilters>({
    role: "all",
    status: "all",
  });
  // The list comes a server page at a time, filtered by the server.
  const query = new URLSearchParams();
  if (filters.role !== "all") query.set("role", filters.role);
  if (filters.status !== "all") query.set("status", filters.status);
  const people = usePagedList<Person>(
    `${PEOPLE_PATH}${query.toString() ? `?${query}` : ""}`,
  );
  const error = streamError(people) || roles.error || catalog.error;

  if (editing) {
    return (
      <PersonEditor
        person={editing === "new" ? undefined : editing}
        roles={roles.data}
        groups={catalog.data}
        scopeOptions={canManage ? scope.data : { companies: [], vehicles: [] }}
        canManage={canManage}
        canManageAccess={canManageAccess}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          people.reload();
        }}
      />
    );
  }

  return (
    <section className="flex flex-col gap-3.5">
      <PageHeader
        title="People and access"
        description="Everyone who can sign in, what they can see and what they can do."
        actions={
          canManage && (
            <Button tone="primary" onClick={() => setEditing("new")}>
              Add person
            </Button>
          )
        }
      />
      {error && <Banner>{error}</Banner>}
      <PeopleList
        items={people.items}
        total={people.total}
        loading={people.loading}
        pendingRows={people.pendingRows}
        failed={Boolean(people.error)}
        roles={roles.data}
        scope={scope.data}
        filters={filters}
        onFilters={setFilters}
        canManage={canManage}
        onEdit={setEditing}
      />
      <ListPager list={people} />
      {can("audit.view") && (
        <RecentChanges
          loading={recent.loading}
          data={recent.data}
          error={recent.error}
        />
      )}
    </section>
  );
}
