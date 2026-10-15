import { Fragment } from "react";

import type {
  PermissionGroup,
  Permission as PermissionItem,
} from "../../lib/types";
import { ListSkeleton } from "../ui";
import type { PersonFormState } from "./usePersonForm";

// The rights of one module, as the API serves them in catalogue order: sections (petty cash) start a column.
function bySection(items: PermissionItem[]) {
  const sections: { name: string | null; items: PermissionItem[] }[] = [];
  for (const item of items) {
    const name = item.section ?? null;
    const last = sections[sections.length - 1];
    if (last && (name === null || last.name === name)) last.items.push(item);
    else sections.push({ name, items: [item] });
  }
  return sections;
}

function ModuleCard({
  group,
  index,
  pf,
  editable,
}: {
  group: PermissionGroup;
  index: number;
  pf: PersonFormState;
  editable: boolean;
}) {
  const { permissions } = pf;
  const sections = bySection(group.items);
  const wide = sections.some((section) => section.name);
  const allOn = group.items.every((item) => permissions.includes(item.key));
  const tick = (item: PermissionItem) => (
    <label key={item.key}>
      <input
        type="checkbox"
        className="pk"
        checked={permissions.includes(item.key)}
        disabled={!editable}
        onChange={(event) => pf.togglePermission(item, event.target.checked)}
      />
      {item.label}
    </label>
  );
  return (
    <div className={wide ? "pg wide" : "pg"} id={`pg-${index}`}>
      <div className="ph">
        <b>{group.name}</b>
        {group.items.length > 1 && (
          <label>
            <input
              type="checkbox"
              checked={allOn}
              disabled={!editable}
              aria-label={`All of ${group.name}`}
              onChange={(event) => pf.setModule(group, event.target.checked)}
            />
            All
          </label>
        )}
      </div>
      {wide ? (
        <div className="pcols">
          {sections.map((section) => (
            <div key={section.name ?? "main"} className="psec">
              {section.name && <span className="pt">{section.name}</span>}
              {section.items.map(tick)}
            </div>
          ))}
        </div>
      ) : (
        <Fragment>{group.items.map(tick)}</Fragment>
      )}
    </div>
  );
}

// The Access pane (v2.32): the tick cards, one per module.
export function AccessPane({
  groups,
  pf,
  ready,
  editable,
  error,
}: {
  groups?: PermissionGroup[];
  pf: PersonFormState;
  ready: boolean;
  editable: boolean;
  error?: string;
}) {
  return (
    <>
      {!ready && (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading permissions</span>
          <ListSkeleton rows={4} />
        </div>
      )}
      {ready && (
        <div className="pgrid">
          {groups!.map((group, index) => (
            <ModuleCard
              key={group.name}
              group={group}
              index={index}
              pf={pf}
              editable={editable}
            />
          ))}
        </div>
      )}
      {error && <div className="ferr">{error}</div>}
    </>
  );
}
