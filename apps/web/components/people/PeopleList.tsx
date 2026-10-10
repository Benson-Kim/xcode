import { formatPhone, plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import type { Person, Role, ScopeOptions } from "../../lib/types";
import {
  CellNote,
  DataTable,
  Hint,
  RowAction,
  RowButton,
  SelectInput,
  StatusBadge,
  Td,
  Toolbar,
  Tr,
} from "../ui";
import {
  changesFromRole,
  roleDefaults,
  scopeLabel,
  type SignInState,
  signInState,
} from "./model";

export type PeopleFilters = {
  role: string;
  status: "all" | SignInState;
};

type Props = {
  items: Person[];
  total: number;
  loading: boolean;
  pendingRows: number;
  failed: boolean;
  roles?: Role[];
  scope?: ScopeOptions;
  filters: PeopleFilters;
  onFilters: (filters: PeopleFilters) => void;
  canManage: boolean;
  onEdit: (person: Person) => void;
};

function SignInBadge({ person }: { person: Person }) {
  const state = signInState(person);
  if (state === "none") return <StatusBadge tone="off">No access</StatusBadge>;
  if (state === "waiting")
    return <StatusBadge tone="warn">Waiting for first sign in</StatusBadge>;
  return <StatusBadge tone="ok">Active</StatusBadge>;
}

function PersonRow({
  person,
  roles,
  scope,
  canManage,
  onEdit,
}: Pick<Props, "roles" | "scope" | "canManage" | "onEdit"> & {
  person: Person;
}) {
  const { kes } = useFormats();
  const changes = changesFromRole(
    person.permissions,
    roleDefaults(roles, person.role),
  );
  return (
    <Tr>
      <Td label="Name">
        <RowButton onClick={() => onEdit(person)}>
          {person.firstName} {person.lastName}
        </RowButton>
        <CellNote>{person.email}</CellNote>
      </Td>
      <Td label="Mobile" numeric>
        {formatPhone(person.phoneNumber)}
      </Td>
      <Td label="Role">
        {person.role}
        {roles && changes > 0 && (
          <CellNote>
            {plural(changes, "change", "changes")} from the role
          </CellNote>
        )}
      </Td>
      <Td label="Can see">
        {scopeLabel(person, scope)}
        {person.approvalLimit ? (
          <CellNote>Approves up to {kes(person.approvalLimit)}</CellNote>
        ) : null}
      </Td>
      <Td label="Sign in">
        <SignInBadge person={person} />
      </Td>
      <Td className="text-right">
        <div className="flex justify-end gap-0.5">
          <RowAction
            aria-label={`${canManage ? "Edit" : "View"} ${person.firstName} ${person.lastName}`}
            onClick={() => onEdit(person)}
          >
            {canManage ? "Edit" : "View"}
          </RowAction>
        </div>
      </Td>
    </Tr>
  );
}

function FilterToolbar(props: Props & { shown: number; filtered: boolean }) {
  const { filters, onFilters } = props;
  return (
    <Toolbar>
      <label
        htmlFor="people-role"
        className="text-[13px] font-semibold text-slate"
      >
        Role
      </label>
      <SelectInput
        id="people-role"
        density="compact"
        inline
        value={filters.role}
        onChange={(event) =>
          onFilters({ ...filters, role: event.target.value })
        }
      >
        <option value="all">All roles</option>
        {(props.roles ?? []).map((role) => (
          <option key={role.id} value={role.name}>
            {role.name}
          </option>
        ))}
      </SelectInput>
      <label
        htmlFor="people-status"
        className="text-[13px] font-semibold text-slate"
      >
        Sign in
      </label>
      <SelectInput
        id="people-status"
        density="compact"
        inline
        value={filters.status}
        onChange={(event) =>
          onFilters({
            ...filters,
            status: event.target.value as PeopleFilters["status"],
          })
        }
      >
        <option value="all">All</option>
        <option value="active">Active</option>
        <option value="waiting">Waiting for first sign in</option>
        <option value="none">No access</option>
      </SelectInput>
      {!props.loading && <Hint>{plural(props.total, "person", "people")}</Hint>}
    </Toolbar>
  );
}

export function PeopleList(props: Props) {
  const { filters, items } = props;
  // The server has filtered the page already.
  const rows = items;
  const filtered = filters.role !== "all" || filters.status !== "all";
  return (
    <>
      <FilterToolbar {...props} shown={rows.length} filtered={filtered} />
      <DataTable
        columns={[
          { label: "Name" },
          { label: "Mobile", numeric: true },
          { label: "Role" },
          { label: "Can see" },
          { label: "Sign in" },
          { label: "Actions", hidden: true },
        ]}
        loading={props.loading}
        pendingRows={props.pendingRows}
        loadingLabel="Loading people"
        isEmpty={!rows.length}
        failed={props.failed}
        emptyMessage={
          filtered && items.length
            ? "Nobody matches these filters."
            : "Nobody in your scope yet."
        }
      >
        {rows.map((person) => (
          <PersonRow
            key={person.id}
            person={person}
            roles={props.roles}
            scope={props.scope}
            canManage={props.canManage}
            onEdit={props.onEdit}
          />
        ))}
      </DataTable>
    </>
  );
}
