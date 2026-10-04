"use client";

import { useState } from "react";
import { apiRequest } from "../lib/data";
import type {
  Page,
  Permission,
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../lib/types";
import { useResource, useStreamedList } from "../lib/data";
import { useSession } from "../lib/session-context";
import { formatDateTime, formatPhone, kes, plural } from "../lib/format";
import type { HistoryRow } from "./setup/shared";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  CardList,
  CardListItem,
  CellNote,
  Chip,
  ChipGroup,
  Choice,
  ChoiceGroup,
  CurrencyInput,
  DataTable,
  ErrorSummary,
  ErrorText,
  Field,
  FormActions,
  FormLayout,
  Grid2,
  GroupLabel,
  Hint,
  ListSkeleton,
  Note,
  PageHeader,
  RowButton,
  SelectInput,
  Skeleton,
  Spacer,
  StatusBadge,
  Tag,
  Td,
  TextInput,
  Toolbar,
  Tr,
  useToast,
} from "./ui";

const APPROVALS = [
  "pettycash.approve_item",
  "pettycash.approve_day",
  "bills.approve",
];

export function PeopleAccessView({
  canManageAccess = false,
}: {
  canManageAccess?: boolean;
}) {
  const { can } = useSession();
  const canManage = can("people.manage") || canManageAccess;
  const people = useStreamedList<Person>("setup/people");
  const roles = useResource<Role[]>("setup/access/roles");
  const catalog = useResource<PermissionGroup[]>("setup/access/catalog");
  const scope = useResource<ScopeOptions>(
    canManage ? "setup/access/scope-options" : null,
  );
  const recent = useResource<Page<HistoryRow>>(
    can("audit.view") ? "setup/history?pageSize=3" : null,
  );
  const [editing, setEditing] = useState<Person | "new" | null>(null);
  const rows = people.items;
  const error = people.error || roles.error || catalog.error;

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
    <section>
      <PageHeader
        title="People and access"
        description="Everyone who can sign in, what they can see and what they can do."
      />
      {error && <Banner className="mt-5">{error}</Banner>}
      <Toolbar>
        {!people.loading && (
          <Hint>{plural(people.total, "person", "people")}</Hint>
        )}
        <Spacer />
        {canManage && (
          <Button onClick={() => setEditing("new")}>Add person</Button>
        )}
      </Toolbar>
      <DataTable
        columns={[
          { label: "Name" },
          { label: "Mobile", numeric: true },
          { label: "Role" },
          { label: "Can see" },
          { label: "Sign in" },
        ]}
        loading={people.loading}
        pendingRows={people.pendingRows}
        loadingLabel="Loading people"
        isEmpty={!rows.length}
        emptyMessage="Nobody in your scope yet."
      >
        {rows.map((person) => {
          const changes = changesFromRole(
            person.permissions,
            roleDefaults(roles.data, person.role),
          );
          return (
            <Tr key={person.id}>
              <Td label="Name">
                <RowButton onClick={() => setEditing(person)}>
                  {person.firstName} {person.lastName}
                </RowButton>
                <CellNote>{person.email}</CellNote>
              </Td>
              <Td label="Mobile" numeric>
                {formatPhone(person.phoneNumber)}
              </Td>
              <Td label="Role">
                {person.role}
                {roles.data && changes > 0 && (
                  <CellNote>
                    {plural(changes, "change", "changes")} from the role
                  </CellNote>
                )}
              </Td>
              <Td label="Can see">
                {scopeLabel(person, scope.data)}
                {person.approvalLimit ? (
                  <CellNote>
                    Approves up to {kes(person.approvalLimit)}
                  </CellNote>
                ) : null}
              </Td>
              <Td label="Sign in">
                {!person.active ? (
                  <StatusBadge tone="off">No access</StatusBadge>
                ) : !person.hasPin ? (
                  <StatusBadge tone="warn">
                    Waiting for first sign in
                  </StatusBadge>
                ) : (
                  <StatusBadge tone="ok">Active</StatusBadge>
                )}
              </Td>
            </Tr>
          );
        })}
      </DataTable>
      {can("audit.view") && (
        <Card className="mt-4">
          <CardHeader
            title="Recent changes"
            description="The latest setup changes. Every change is in the change log."
          />
          {recent.loading ? (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading recent changes</span>
              <ListSkeleton rows={3} />
            </div>
          ) : recent.data?.items.length ? (
            <CardList>
              {recent.data.items.map((row) => (
                <CardListItem
                  key={row.version}
                  left={row.reason}
                  leftSub={row.actorName}
                  rightSub={formatDateTime(row.occurredAt)}
                />
              ))}
            </CardList>
          ) : (
            <Hint>{recent.error || "No changes yet."}</Hint>
          )}
        </Card>
      )}
    </section>
  );
}

function roleDefaults(roles: Role[] | undefined, role: string) {
  return roles?.find((candidate) => candidate.name === role)?.permissions ?? [];
}

function changesFromRole(permissions: string[], defaults: string[]) {
  return (
    permissions.filter((key) => !defaults.includes(key)).length +
    defaults.filter((key) => !permissions.includes(key)).length
  );
}

function scopeLabel(person: Person, options?: ScopeOptions) {
  if (person.scopeMode === "all") return "All companies";
  if (person.scopeMode === "companies") {
    if (person.otherCompanies > 0) {
      const total = person.companyIds.length + person.otherCompanies;
      return `${plural(total, "company", "companies")} (${person.otherCompanies} hidden)`;
    }
    const names = person.companyIds
      .map(
        (id) => options?.companies.find((company) => company.id === id)?.name,
      )
      .filter(Boolean);
    return names.length === person.companyIds.length && names.length <= 2
      ? names.join(", ")
      : plural(person.companyIds.length, "company", "companies");
  }
  if (person.otherVehicles > 0) {
    const total = person.vehicleIds.length + person.otherVehicles;
    return `${plural(total, "vehicle", "vehicles")} (${person.otherVehicles} hidden)`;
  }
  return plural(person.vehicleIds.length, "vehicle", "vehicles");
}

// Ticking a permission ticks what it needs; unticking one unticks what depends on it.
function withNeeds(selected: string[], key: string, all: Permission[]) {
  const next = new Set([...selected, key]);
  const pending = [key];
  while (pending.length) {
    // Taken off the list before the search, not inside it: find() would call the test once per permission
    // and pop a fresh key each time, so it only ever matched one that happens to be listed first.
    const current = pending.pop();
    for (const need of all.find((item) => item.key === current)?.needs ?? []) {
      if (next.has(need)) continue;
      next.add(need);
      pending.push(need);
    }
  }
  return [...next];
}

function withoutDependents(selected: string[], key: string, all: Permission[]) {
  const removed = new Set([key]);
  let changed = true;
  while (changed) {
    changed = false;
    for (const item of all) {
      if (
        removed.has(item.key) ||
        !selected.includes(item.key) ||
        !item.needs.some((need) => removed.has(need))
      )
        continue;
      removed.add(item.key);
      changed = true;
    }
  }
  return selected.filter((item) => !removed.has(item));
}

function normalisePhone(value: string) {
  const digits = value.replace(/\D/g, "");
  if (digits.startsWith("254")) return `0${digits.slice(3)}`;
  if (/^[17]/.test(digits)) return `0${digits}`;
  return digits;
}

type Errors = Partial<
  Record<
    | "firstName"
    | "lastName"
    | "phoneNumber"
    | "email"
    | "role"
    | "scope"
    | "permissions",
    string
  >
>;

function PersonEditor({
  person,
  roles,
  groups,
  scopeOptions,
  canManage,
  canManageAccess,
  onClose,
  onSaved,
}: {
  person?: Person;
  // Each arrives on its own request; until then its section shows placeholders.
  roles?: Role[];
  groups?: PermissionGroup[];
  scopeOptions?: ScopeOptions;
  canManage: boolean;
  canManageAccess: boolean;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { session } = useSession();
  const toast = useToast();
  const initialRole = person?.role ?? "Revenue clerk";
  const [form, setForm] = useState({
    firstName: person?.firstName ?? "",
    lastName: person?.lastName ?? "",
    phoneNumber: person ? formatPhone(person.phoneNumber) : "",
    email: person?.email ?? "",
    role: initialRole,
    scopeMode: person?.scopeMode ?? "vehicles",
    companyIds: person?.companyIds ?? [],
    vehicleIds: person?.vehicleIds ?? [],
    // null until the person changes a permission: the role's defaults apply, whenever the roles arrive.
    permissions: (person?.permissions ?? null) as string[] | null,
    approvalLimit: person?.approvalLimit ? String(person.approvalLimit) : "",
  });
  const [errors, setErrors] = useState<Errors>({});
  const [saveError, setSaveError] = useState("");
  const [permissionNote, setPermissionNote] = useState("");
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [removeReason, setRemoveReason] = useState("");
  const [busy, setBusy] = useState(false);

  const self = Boolean(person && person.id === session?.userId);
  const ownerLock = person?.role === "Owner" && session?.role !== "Owner";
  const editable = canManage && !self && !ownerLock;
  const permissionsEditable = editable && canManageAccess;
  const all = (groups ?? []).flatMap((group) => group.items);
  const permissionsReady = Boolean(roles && groups);
  const label = (key: string) =>
    all.find((item) => item.key === key)?.label ?? key;
  const assignableRoles = (roles ?? []).filter(
    (role) =>
      role.name === person?.role ||
      session?.role === "Owner" ||
      (role.name !== "Owner" &&
        role.permissions.every((permission) =>
          session?.permissions.includes(permission),
        )),
  );
  const selectedRole =
    assignableRoles.find((role) => role.name === form.role)?.name ??
    assignableRoles[0]?.name ??
    (roles ? "" : form.role);
  const defaults = roleDefaults(roles, selectedRole);
  const permissions = form.permissions ?? defaults;
  const changes = changesFromRole(permissions, defaults);
  const needsLimit = permissions.some((key) => APPROVALS.includes(key));
  const name = `${form.firstName.trim()} ${form.lastName.trim()}`.trim();

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
    setForm({ ...form, permissions: next });
  }

  function toggleScope(
    key: "companyIds" | "vehicleIds",
    id: string,
    checked: boolean,
  ) {
    setForm({
      ...form,
      [key]: checked
        ? [...form[key], id]
        : form[key].filter((value) => value !== id),
    });
  }

  async function save() {
    const phone = normalisePhone(form.phoneNumber);
    const next: Errors = {};
    if (!form.firstName.trim()) next.firstName = "Enter a first name.";
    if (!form.lastName.trim()) next.lastName = "Enter a last name.";
    if (!/^0[17][0-9]{8}$/.test(phone))
      next.phoneNumber = "Enter all 10 numbers, starting 07 or 01.";
    if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(form.email.trim()))
      next.email = "Enter an email address like name@company.co.ke";
    if (roles && !assignableRoles.length)
      next.role = "You cannot assign any available role.";
    if (form.scopeMode === "companies" && !form.companyIds.length)
      next.scope = "Tick at least one company.";
    if (form.scopeMode === "vehicles" && !form.vehicleIds.length)
      next.scope = "Tick at least one vehicle.";
    if (!permissions.length) next.permissions = "Tick at least one permission.";
    setErrors(next);
    setSaveError("");
    if (Object.keys(next).length) return;
    setBusy(true);
    try {
      await apiRequest(person ? `setup/people/${person.id}` : "setup/people", {
        method: person ? "PUT" : "POST",
        body: JSON.stringify({
          firstName: form.firstName.trim(),
          lastName: form.lastName.trim(),
          email: form.email.trim(),
          phoneNumber: phone,
          role: selectedRole,
          scopeMode: form.scopeMode,
          companyIds: form.scopeMode === "companies" ? form.companyIds : [],
          vehicleIds: form.scopeMode === "vehicles" ? form.vehicleIds : [],
          permissions,
          approvalLimit:
            needsLimit && form.approvalLimit
              ? Number(form.approvalLimit)
              : null,
          version: person?.version,
        }),
      });
      toast(
        person
          ? `Changes saved for ${name}.`
          : `${name} added. They sign in with ${formatPhone(phone)} and set a PIN with an email code.`,
      );
      onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function lifecycle(action: "activate" | "deactivate" | "sign-out") {
    if (!person) return;
    if (action === "deactivate" && !confirmRemove)
      return setConfirmRemove(true);
    setBusy(true);
    try {
      await apiRequest(`setup/people/${person.id}/${action}`, {
        method: "POST",
        ...(action === "sign-out"
          ? {}
          : {
              body: JSON.stringify({
                version: person.version,
                ...(action === "deactivate"
                  ? { reason: removeReason.trim() }
                  : {}),
              }),
            }),
      });
      toast(
        action === "sign-out"
          ? `${person.firstName} is signed out of every device.`
          : action === "activate"
            ? "Access given back."
            : `Access removed for ${person.firstName} ${person.lastName}.`,
      );
      if (action === "sign-out") setBusy(false);
      else onSaved();
    } catch (value) {
      setSaveError((value as Error).message);
      if (action !== "deactivate") setConfirmRemove(false);
      setBusy(false);
    }
  }

  const options = scopeOptions ?? { companies: [], vehicles: [] };
  const companiesWithVehicles = options.companies
    .map((company) => ({
      ...company,
      vehicles: options.vehicles.filter(
        (vehicle) => vehicle.companyId === company.id,
      ),
    }))
    .filter((company) => company.vehicles.length);
  const unlistedVehicles = options.vehicles.filter(
    (vehicle) =>
      !options.companies.some((company) => company.id === vehicle.companyId),
  );

  return (
    <section>
      <PageHeader
        title={person ? `${person.firstName} ${person.lastName}` : "Add person"}
        description={
          person
            ? `Mobile ${formatPhone(person.phoneNumber)}`
            : "They sign in with this mobile number and set their own PIN with an email code."
        }
      />
      <FormLayout>
        <ErrorSummary count={Object.keys(errors).length} />
        {saveError && <Banner>{saveError}</Banner>}
        {!canManage ? (
          <Note>You can view people but not change them.</Note>
        ) : self ? (
          <Note>
            This is you. Someone else who manages people changes your details
            and access.
          </Note>
        ) : ownerLock ? (
          <Note>Only the owner can change the owner&apos;s access.</Note>
        ) : null}
        {person && !person.active && (
          <Note>This person has no access. They cannot sign in.</Note>
        )}

        <Card density="form">
          <CardHeader title="Details" />
          <Grid2>
            <Field
              id="person-first"
              label="First name"
              error={errors.firstName}
            >
              <TextInput
                value={form.firstName}
                disabled={!editable}
                autoComplete="off"
                onChange={(event) =>
                  setForm({ ...form, firstName: event.target.value })
                }
              />
            </Field>
            <Field id="person-last" label="Last name" error={errors.lastName}>
              <TextInput
                value={form.lastName}
                disabled={!editable}
                autoComplete="off"
                onChange={(event) =>
                  setForm({ ...form, lastName: event.target.value })
                }
              />
            </Field>
            <Field
              id="person-mobile"
              label="Mobile number"
              error={errors.phoneNumber}
              hint="Used to sign in. Changing it signs them out of every device."
            >
              <TextInput
                type="tel"
                inputMode="numeric"
                placeholder="0712 345 678"
                value={form.phoneNumber}
                disabled={!editable}
                onChange={(event) =>
                  setForm({ ...form, phoneNumber: event.target.value })
                }
              />
            </Field>
            <Field
              id="person-email"
              label="Email"
              error={errors.email}
              hint="Only used to send one time codes. Changing it signs them out of every device."
            >
              <TextInput
                type="email"
                autoCapitalize="none"
                spellCheck={false}
                placeholder="name@company.co.ke"
                value={form.email}
                disabled={!editable}
                onChange={(event) =>
                  setForm({ ...form, email: event.target.value })
                }
              />
            </Field>
          </Grid2>
        </Card>

        <Card density="form">
          <CardHeader
            title="Role"
            description="A starting set of permissions. You can change single permissions further down."
          />
          <Field
            id="person-role"
            label="Role"
            error={errors.role}
            hint={
              person
                ? "Changing the role resets single permissions to the new role."
                : roles && !assignableRoles.length
                  ? "You cannot assign any available role."
                : undefined
            }
          >
            {!roles ? (
              <Skeleton className="h-12 rounded-[10px]" />
            ) : (
              <SelectInput
                value={selectedRole}
                disabled={!editable || !assignableRoles.length}
                onChange={(event) => {
                  const role = event.target.value;
                  setPermissionNote("");
                  setForm({
                    ...form,
                    role,
                    permissions: null,
                    scopeMode: role === "Owner" ? "all" : form.scopeMode,
                  });
                }}
              >
                {assignableRoles.map((role) => (
                  <option key={role.id} value={role.name}>
                    {role.name}
                  </option>
                ))}
              </SelectInput>
            )}
          </Field>
        </Card>

        <Card density="form">
          <CardHeader
            title="What they can see"
            description="Every number, list and report is limited to this."
          />
          <ChoiceGroup role="radiogroup" label="What they can see">
            {[
              { value: "all", label: "All companies" },
              { value: "companies", label: "Chosen companies" },
              { value: "vehicles", label: "Chosen vehicles" },
            ].map((option) => (
              <Choice
                key={option.value}
                type="radio"
                name="person-scope"
                label={option.label}
                checked={form.scopeMode === option.value}
                disabled={!editable || selectedRole === "Owner"}
                onChange={() => setForm({ ...form, scopeMode: option.value })}
              />
            ))}
          </ChoiceGroup>
          {form.scopeMode !== "all" && !scopeOptions ? (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading what they can see</span>
              <ListSkeleton rows={2} />
            </div>
          ) : form.scopeMode === "companies" && scopeOptions ? (
            <ChoiceGroup label="Companies they can see">
              {scopeOptions.companies.map((company) => (
                <Choice
                  key={company.id}
                  label={company.name}
                  checked={form.companyIds.includes(company.id)}
                  disabled={!editable}
                  onChange={(event) =>
                    toggleScope("companyIds", company.id, event.target.checked)
                  }
                />
              ))}
              {!scopeOptions.companies.length && (
                <Hint>
                  There are no companies in your own scope to choose from.
                </Hint>
              )}
            </ChoiceGroup>
          ) : form.scopeMode === "vehicles" && scopeOptions ? (
            <div role="group" aria-label="Vehicles they can see">
              {[
                ...companiesWithVehicles,
                ...(unlistedVehicles.length
                  ? [{ id: "", name: "", vehicles: unlistedVehicles }]
                  : []),
              ].map((company) => (
                <div key={company.id || "other"}>
                  {company.name && <GroupLabel>{company.name}</GroupLabel>}
                  <ChoiceGroup>
                    {company.vehicles.map((vehicle) => (
                      <Choice
                        key={vehicle.id}
                        label={vehicle.registration}
                        checked={form.vehicleIds.includes(vehicle.id)}
                        disabled={!editable}
                        onChange={(event) =>
                          toggleScope(
                            "vehicleIds",
                            vehicle.id,
                            event.target.checked,
                          )
                        }
                      />
                    ))}
                  </ChoiceGroup>
                </div>
              ))}
              {!scopeOptions.vehicles.length && (
                <Hint>
                  There are no vehicles in your own scope to choose from.
                </Hint>
              )}
            </div>
          ) : (
            <Hint>
              {selectedRole === "Owner"
                ? "The owner always sees every company."
                : "Includes any company added later."}
            </Hint>
          )}
          {errors.scope && <ErrorText>{errors.scope}</ErrorText>}
        </Card>

        <Card density="form">
          <CardHeader
            title="Permissions"
            description={
              !permissionsReady
                ? undefined
                : `${permissions.length} ticked. ${changes ? `${plural(changes, "change", "changes")} from the ${selectedRole} role, marked below.` : `Same as the ${selectedRole} role.`}`
            }
          />
          {editable && !canManageAccess && (
            <Note>
              Changing single permissions needs &ldquo;{label("access.manage")}
              &rdquo;. The role&apos;s permissions apply.
            </Note>
          )}
          {permissionNote && (
            <Note tone="info" role="status">
              {permissionNote}
            </Note>
          )}
          {permissionsEditable && changes > 0 && (
            <ChipGroup>
              <Chip
                onClick={() => {
                  setPermissionNote("");
                  setForm({ ...form, permissions: null });
                }}
              >
                Match the role again
              </Chip>
            </ChipGroup>
          )}
          {!permissionsReady && (
            <div role="status" aria-busy="true">
              <span className="sr-only">Loading permissions</span>
              <ListSkeleton rows={4} />
            </div>
          )}
          {permissionsReady &&
            groups!.map((group) => (
              <div key={group.name} className="border-t border-divider pt-3">
                <h3 className="m-0 mb-1 flex justify-between gap-2 text-[15px] font-bold">
                  {group.name}
                  <small className="text-[13px] font-medium text-grey">
                    {
                      group.items.filter((item) =>
                        permissions.includes(item.key),
                      ).length
                    }{" "}
                    of {group.items.length}
                  </small>
                </h3>
                {group.items.map((item) => {
                  const ticked = permissions.includes(item.key);
                  const inRole = defaults.includes(item.key);
                  return (
                    <Choice
                      key={item.key}
                      label={
                        <>
                          {item.label}
                          {ticked && !inRole && <Tag tone="add">Added</Tag>}
                          {!ticked && inRole && (
                            <Tag tone="remove">Removed</Tag>
                          )}
                        </>
                      }
                      aria-label={item.label}
                      description={
                        item.needs.length
                          ? `Needs: ${item.needs.map(label).join(", ")}`
                          : undefined
                      }
                      checked={ticked}
                      disabled={!permissionsEditable}
                      onChange={(event) =>
                        togglePermission(item, event.target.checked)
                      }
                    />
                  );
                })}
              </div>
            ))}
          {errors.permissions && <ErrorText>{errors.permissions}</ErrorText>}
        </Card>

        {needsLimit && (
          <Card density="form">
            <CardHeader
              title="Approval limit"
              description="The most they can approve in one entry."
            />
            <Field
              id="person-limit"
              label="Limit per entry"
              hint="Leave empty for no limit."
            >
              <CurrencyInput
                min="0"
                step="1"
                value={form.approvalLimit}
                disabled={!permissionsEditable}
                onChange={(event) =>
                  setForm({ ...form, approvalLimit: event.target.value })
                }
              />
            </Field>
          </Card>
        )}

        {confirmRemove && person?.active && editable && (
          <Card density="form">
            <CardHeader
              title="Reason for removing access"
              description="A short reason is required and is kept in the change log."
            />
            <Field id="remove-reason" label="Reason">
              <TextInput
                value={removeReason}
                maxLength={500}
                autoComplete="off"
                placeholder="For example, left the organization"
                onChange={(event) => setRemoveReason(event.target.value)}
              />
            </Field>
          </Card>
        )}

        <FormActions>
          {editable && (
            <Button
              disabled={busy || !permissionsReady}
              onClick={() => void save()}
            >
              {person ? "Save changes" : "Save person"}
            </Button>
          )}
          <Button tone="outline" onClick={onClose}>
            {editable ? "Cancel" : "Back"}
          </Button>
          <Spacer />
          {editable && person && (
            <>
              <Button
                tone="outline"
                disabled={busy}
                onClick={() => void lifecycle("sign-out")}
              >
                Sign out of all devices
              </Button>
              {person.active ? (
                <Button
                  tone="danger"
                  disabled={busy}
                  onClick={() => void lifecycle("deactivate")}
                >
                  {confirmRemove ? "Confirm removal" : "Remove access"}
                </Button>
              ) : (
                <Button
                  tone="outline"
                  disabled={busy}
                  onClick={() => void lifecycle("activate")}
                >
                  Give access back
                </Button>
              )}
            </>
          )}
        </FormActions>
      </FormLayout>
    </section>
  );
}
