import { plural } from "@xcode/shared/format";

import type { PermissionGroup } from "../../lib/types";
import { Chip, ChipGroup, ErrorText, ListSkeleton, Note, Tag } from "../ui";
import { FormSection, SectionLabel } from "./PersonCards";
import type { PersonFormState } from "./usePersonForm";

type Props = {
  groups?: PermissionGroup[];
  pf: PersonFormState;
  ready: boolean;
  editable: boolean;
  canManageAccess: boolean;
  error?: string;
};

function PermissionGroupList({
  group,
  pf,
  editable,
}: {
  group: PermissionGroup;
  pf: PersonFormState;
  editable: boolean;
}) {
  const { permissions, defaults, label } = pf;
  return (
    <div className="pg">
      <h4 className="ph">
        <b>{group.name}</b>
        <small className="hint">
          {group.items.filter((item) => permissions.includes(item.key)).length}{" "}
          of {group.items.length}
        </small>
      </h4>
      {group.items.map((item) => {
        const ticked = permissions.includes(item.key);
        const inRole = defaults.includes(item.key);
        return (
          <label key={item.key}>
            <input
              type="checkbox"
              aria-label={item.label}
              checked={ticked}
              disabled={!editable}
              onChange={(event) =>
                pf.togglePermission(item, event.target.checked)
              }
            />
            <span>
              {item.label}
              {ticked && !inRole && <Tag tone="add">Added</Tag>}
              {!ticked && inRole && <Tag tone="remove">Removed</Tag>}
              {item.needs.length > 0 && (
                <>
                  <br />
                  <small className="hint">
                    {`Needs: ${item.needs.map(label).join(", ")}`}
                  </small>
                </>
              )}
            </span>
          </label>
        );
      })}
    </div>
  );
}

export function PermissionsCard({
  groups,
  pf,
  ready,
  editable,
  canManageAccess,
  error,
}: Props) {
  const { permissions, changes, selectedRole } = pf;
  const permissionsEditable = editable && canManageAccess;
  return (
    <FormSection>
      <SectionLabel
        title="Access"
        description={
          !ready
            ? undefined
            : `${permissions.length} ticked. ${changes ? `${plural(changes, "change", "changes")} from the ${selectedRole} role, marked below.` : `Same as the ${selectedRole} role.`}`
        }
      />
      {editable && !canManageAccess && (
        <Note>
          Changing single permissions needs &ldquo;{pf.label("access.manage")}
          &rdquo;. The role&apos;s permissions apply.
        </Note>
      )}
      {pf.permissionNote && (
        <Note tone="info" role="status">
          {pf.permissionNote}
        </Note>
      )}
      {permissionsEditable && changes > 0 && (
        <ChipGroup>
          <Chip onClick={pf.resetPermissions}>Match the role again</Chip>
        </ChipGroup>
      )}
      {!ready && (
        <div role="status" aria-busy="true">
          <span className="sr-only">Loading permissions</span>
          <ListSkeleton rows={4} />
        </div>
      )}
      {ready && (
        <div className="pgrid">
          {groups!.map((group) => (
            <PermissionGroupList
              key={group.name}
              group={group}
              pf={pf}
              editable={permissionsEditable}
            />
          ))}
        </div>
      )}
      {error && <ErrorText>{error}</ErrorText>}
    </FormSection>
  );
}
