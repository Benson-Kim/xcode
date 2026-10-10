import { formatPhone, plural } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import type { Person, Role, ScopeOptions } from "../../lib/types";
import {
  CellNote,
  DataTable,
  Hint,
  RowAction,
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
  // How many permissions there are, for each person's share of them; unknown until the catalog loads.
  permissionTotal?: number;
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

// The person's permissions as a share of all of them (.prog), with how far they are from their role on hover.
function AccessBar({
  count,
  total,
  title,
}: {
  count: number;
  total?: number;
  title?: string;
}) {
  const share = total ? Math.min(100, Math.round((count / total) * 100)) : 0;
  return (
    <div className="prog" title={title}>
      {total ? (
        <div className="t" aria-hidden="true">
          <i
            className={share === 100 ? "full" : undefined}
            style={{ width: `${share}%` }}
          />
        </div>
      ) : null}
      <span>{total ? `${count} of ${total}` : count}</span>
    </div>
  );
}

function PersonRow({
  person,
  roles,
  scope,
  permissionTotal,
  canManage,
  onEdit,
}: Pick<
  Props,
  "roles" | "scope" | "permissionTotal" | "canManage" | "onEdit"
> & {
  person: Person;
}) {
  const { kes } = useFormats();
  const changes = changesFromRole(
    person.permissions,
    roleDefaults(roles, person.role),
  );
  return (
    <Tr>
      <Td label="Name" className="item" title={person.email}>
        {person.firstName} {person.lastName}
        <CellNote>{person.role}</CellNote>
      </Td>
      <Td label="Mobile number" className="num nw">
        {formatPhone(person.phoneNumber)}
      </Td>
      <Td label="Access">
        <AccessBar
          count={person.permissions.length}
          total={permissionTotal}
          title={
            roles && changes > 0
              ? `${plural(changes, "change", "changes")} from the role`
              : undefined
          }
        />
      </Td>
      <Td
        label="Vehicles"
        className="nw"
        title={
          person.approvalLimit
            ? `Approves up to ${kes(person.approvalLimit)}`
            : undefined
        }
      >
        {scopeLabel(person, scope)}
      </Td>
      <Td label="Status" className="nw">
        <SignInBadge person={person} />
      </Td>
      <Td numeric>
        <div className="tacts">
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
      <label htmlFor="people-role" className="sr-only">
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
      <label htmlFor="people-status" className="sr-only">
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
          { label: "Mobile number" },
          { label: "Access" },
          { label: "Vehicles" },
          { label: "Status" },
          { label: "Actions", numeric: true },
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
            permissionTotal={props.permissionTotal}
            canManage={props.canManage}
            onEdit={props.onEdit}
          />
        ))}
      </DataTable>
    </>
  );
}
