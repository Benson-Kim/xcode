"use client";

import { useState } from "react";

import { useAppearance } from "../lib/appearance";
import { streamError, useResource } from "../lib/data";
import {
  CATALOG_PATH,
  PEOPLE_PATH,
  ROLES_PATH,
  SCOPE_PATH,
} from "../lib/endpoints/people";
import { useSession } from "../lib/session-context";
import type {
  MyScope,
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../lib/types";
import { BlockDialog } from "./people/BlockDialog";
import { PeopleList } from "./people/PeopleList";
import { PersonEditor } from "./people/PersonEditor";
import { Banner, Button, ListPager, PageHeader, useToast } from "./ui";
import { usePagedList } from "./usePagedList";

// People and access (v2.32, v2.33): one row a person, with what they can reach by module, their vehicles, how far
// back they may change records, and where they are with signing in. Edit opens the person pop up; Block and
// Unblock act from the row.
export function PeopleAccessView({
  canManageAccess = false,
}: {
  canManageAccess?: boolean;
}) {
  const { can, session } = useSession();
  const { appearance } = useAppearance();
  const toast = useToast();
  const legacy = can("people.manage") || canManageAccess;
  const canAdd = can("people.add") || legacy;
  const canEdit = can("people.edit") || legacy;
  const canBlock = can("people.block") || legacy;
  const canSignIn = can("people.sign_in") || legacy;
  const canManage = canAdd || canEdit;
  const roles = useResource<Role[]>(ROLES_PATH);
  const catalog = useResource<PermissionGroup[]>(CATALOG_PATH);
  const scope = useResource<ScopeOptions>(canManage ? SCOPE_PATH : null);
  const mine = useResource<MyScope>(canManage ? "setup/access/me" : null);
  const [editing, setEditing] = useState<Person | "new" | null>(null);
  const [blocking, setBlocking] = useState<Person | null>(null);
  // The list comes a server page at a time.
  const people = usePagedList<Person>(PEOPLE_PATH);
  const error = streamError(people) || roles.error || catalog.error;
  const today = appearance?.businessDate ?? "";

  const editor = editing && (
    <PersonEditor
      person={editing === "new" ? undefined : editing}
      roles={roles.data}
      groups={catalog.data}
      scopeOptions={canManage ? scope.data : { companies: [], vehicles: [] }}
      fullScope={mine.data?.allCompanies ?? false}
      today={today}
      canManage={editing === "new" ? canAdd : canEdit}
      canSignIn={canSignIn}
      onClose={() => setEditing(null)}
      onSaved={(name, isNew) => {
        setEditing(null);
        people.reload();
        toast(
          isNew
            ? `Saved. ${name.split(" ")[0]} sets a PIN at first sign in.`
            : "Saved",
        );
      }}
      onChanged={people.reload}
    />
  );

  return (
    <>
      <PageHeader
        title="People and access"
        actions={
          canAdd && (
            <Button tone="primary" onClick={() => setEditing("new")}>
              New person
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
        scope={scope.data}
        canEdit={canEdit}
        canBlock={canBlock}
        selfId={session?.userId}
        onEdit={setEditing}
        onBlock={setBlocking}
      />
      <ListPager list={people} />
      {editor}
      {blocking && (
        <BlockDialog
          person={blocking}
          onDone={() => {
            setBlocking(null);
            people.reload();
          }}
          onClose={() => setBlocking(null)}
        />
      )}
    </>
  );
}
