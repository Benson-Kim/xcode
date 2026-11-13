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
import { DeletePersonDialog } from "./people/DeletePersonDialog";
import { EraseDialog } from "./people/EraseDialog";
import { PeopleList } from "./people/PeopleList";
import { PersonEditor } from "./people/PersonEditor";
import type { RemovalAction } from "./people/RemovePane";
import { Banner, Button, ListPager, PageHeader, useToast } from "./ui";
import { usePagedList } from "./usePagedList";

// People and access (v2.32, v2.33): one row a person, with what they can reach by module, their vehicles, how far
// back they may change records, and where they are with signing in. Edit opens the person pop up; Block, Unblock
// and Erase are on the row too.
export function PeopleAccessView() {
  const { can, session } = useSession();
  const { appearance } = useAppearance();
  const toast = useToast();
  // Each action needs the right the API checks for it: people.manage is derived from any of these, so it gates none.
  const canAdd = can("people.add");
  const canEdit = can("people.edit");
  const canBlock = can("people.block");
  const canDelete = canBlock;
  const canSignIn = can("people.sign_in");
  const canManage = canAdd || canEdit;
  const roles = useResource<Role[]>(ROLES_PATH);
  const catalog = useResource<PermissionGroup[]>(CATALOG_PATH);
  const scope = useResource<ScopeOptions>(canManage ? SCOPE_PATH : null);
  const mine = useResource<MyScope>(canManage ? "setup/access/me" : null);
  const [editing, setEditing] = useState<Person | "new" | null>(null);
  const [blocking, setBlocking] = useState<Person | null>(null);
  const [erasing, setErasing] = useState<Person | null>(null);
  const [deleting, setDeleting] = useState<Person | null>(null);
  // The list comes a server page at a time.
  const people = usePagedList<Person>(PEOPLE_PATH);
  const error = streamError(people) || roles.error || catalog.error;
  const today = appearance?.businessDate ?? "";
  const done = () => {
    setBlocking(null);
    setErasing(null);
    setDeleting(null);
    people.reload();
  };
  // Block, Erase and Delete each confirm in their own dialog, opened from the row or the person pop up.
  const startRemoval = (person: Person, action: RemovalAction) => {
    setEditing(null);
    setDeleting(null);
    if (action === "block") setBlocking(person);
    else if (action === "erase") setErasing(person);
    else setDeleting(person);
  };

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
      canBlock={canBlock}
      canDelete={canDelete}
      onRemoval={startRemoval}
      onClose={() => setEditing(null)}
      onSaved={(_name, isNew, email) => {
        setEditing(null);
        people.reload();
        toast(isNew ? `Saved. Invitation emailed to ${email}.` : "Saved");
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
        viewer={session}
        onEdit={setEditing}
        onRemoval={startRemoval}
      />
      <ListPager list={people} />
      {editor}
      {blocking && (
        <BlockDialog
          person={blocking}
          onDone={done}
          onClose={() => setBlocking(null)}
        />
      )}
      {erasing && (
        <EraseDialog
          person={erasing}
          onDone={done}
          onClose={() => setErasing(null)}
        />
      )}
      {deleting && (
        <DeletePersonDialog
          person={deleting}
          onDone={done}
          onClose={() => setDeleting(null)}
          onInstead={(action) => startRemoval(deleting, action)}
        />
      )}
    </>
  );
}
