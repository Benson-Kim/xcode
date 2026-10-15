import { formatPhone, initials } from "@xcode/shared/format";

import { useFormats } from "../../lib/formats";
import type { Person, ScopeOptions } from "../../lib/types";
import { DataTable, RowAction, Td, Tr } from "../ui";
import { FLOAT_RIGHT, personStatus, scopeLabel, STATUS_CHIPS } from "./model";

type Props = {
  items: Person[];
  total: number;
  loading: boolean;
  pendingRows: number;
  failed: boolean;
  scope?: ScopeOptions;
  canEdit: boolean;
  canBlock: boolean;
  selfId?: string;
  onEdit: (person: Person) => void;
  onBlock: (person: Person) => void;
};

export function StatusChip({ person }: { person: Person }) {
  const chip = STATUS_CHIPS[personStatus(person)];
  return <span className={`chip ${chip.tone}`}>{chip.label}</span>;
}

// What the person can reach, one chip per module: filled when they hold every right in it, outlined with "4 of 20"
// when partial, "Everything" for all of them (v2.32).
export function ModuleChips({ person }: { person: Person }) {
  if (person.everything)
    return (
      <div className="mchips">
        <span className="mchip">Everything</span>
      </div>
    );
  const held = (person.modules ?? []).filter((module) => module.held > 0);
  return (
    <div className="mchips">
      {held.length ? (
        held.map((module) => (
          <span
            key={module.name}
            className={module.held < module.total ? "mchip part" : "mchip"}
          >
            {module.name}
            {module.held < module.total && (
              <i>
                {module.held} of {module.total}
              </i>
            )}
          </span>
        ))
      ) : (
        <span className="muted">No access</span>
      )}
    </div>
  );
}

function PersonRow({
  person,
  scope,
  canEdit,
  canBlock,
  selfId,
  onEdit,
  onBlock,
}: Omit<Props, "items" | "total" | "loading" | "pendingRows" | "failed"> & {
  person: Person;
}) {
  const { formatDateTime } = useFormats();
  const blocked = personStatus(person) === "blocked";
  const name = `${person.firstName} ${person.lastName}`;
  return (
    <Tr>
      <Td label="Person">
        <div className="pcell">
          <span className={blocked ? "av2 off" : "av2"} aria-hidden="true">
            {initials(person.firstName, person.lastName)}
          </span>
          <div>
            <b>
              {name}
              {person.permissions.includes(FLOAT_RIGHT) && (
                <span className="chip mute">Float</span>
              )}
            </b>
            <span className="note">
              {person.role} · {formatPhone(person.phoneNumber)}
            </span>
          </div>
        </div>
      </Td>
      <Td label="Access">
        <ModuleChips person={person} />
      </Td>
      <Td label="Vehicles" className="nw">
        {scopeLabel(person, scope)}
      </Td>
      <Td label="Can change" className="pback">
        {person.canChange ?? "Any date"}
      </Td>
      <Td label="Status" className="pst">
        <StatusChip person={person} />
        {person.lastSignedInAt && (
          <span className="note">{formatDateTime(person.lastSignedInAt)}</span>
        )}
      </Td>
      <Td numeric>
        <div className="tacts">
          {canEdit && (
            <RowAction
              aria-label={`Edit ${name}`}
              onClick={() => onEdit(person)}
            >
              Edit
            </RowAction>
          )}
          {!canEdit && (
            <RowAction
              aria-label={`View ${name}`}
              onClick={() => onEdit(person)}
            >
              View
            </RowAction>
          )}
          {canBlock && person.id !== selfId && (
            <button
              type="button"
              className={blocked ? "act ok" : "act bad"}
              aria-label={`${blocked ? "Unblock" : "Block"} ${name}`}
              onClick={() => onBlock(person)}
            >
              {blocked ? "Unblock" : "Block"}
            </button>
          )}
        </div>
      </Td>
    </Tr>
  );
}

export function PeopleList(props: Props) {
  const { items } = props;
  return (
    <DataTable
      columns={[
        { label: "Person" },
        { label: "Access" },
        { label: "Vehicles" },
        { label: "Can change" },
        { label: "Status" },
        { label: "Actions", numeric: true },
      ]}
      loading={props.loading}
      pendingRows={props.pendingRows}
      loadingLabel="Loading people"
      isEmpty={!items.length}
      failed={props.failed}
      emptyMessage="Nobody in your scope yet."
    >
      {items.map((person) => (
        <PersonRow
          key={person.id}
          person={person}
          scope={props.scope}
          canEdit={props.canEdit}
          canBlock={props.canBlock}
          selfId={props.selfId}
          onEdit={props.onEdit}
          onBlock={props.onBlock}
        />
      ))}
    </DataTable>
  );
}
