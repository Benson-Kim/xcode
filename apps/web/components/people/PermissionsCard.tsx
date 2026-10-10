import { plural } from "@xcode/shared/format";

import type { PermissionGroup } from "../../lib/types";
import {
  CardHeader,
  Chip,
  ChipGroup,
  ErrorText,
  ListSkeleton,
  Note,
  Tag,
} from "../ui";
import { FormSection } from "./PersonCards";
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
    <div className="overflow-hidden rounded-xl border border-line">
      <h3 className="m-0 flex items-center justify-between gap-2.5 border-b border-line bg-paper px-3.5 py-2.5 text-[14.5px] font-bold text-ink">
        {group.name}
        <small className="text-[13px] font-bold text-slate">
          {group.items.filter((item) => permissions.includes(item.key)).length}{" "}
          of {group.items.length}
        </small>
      </h3>
      {group.items.map((item) => {
        const ticked = permissions.includes(item.key);
        const inRole = defaults.includes(item.key);
        return (
          <label
            key={item.key}
            className="flex cursor-pointer items-start gap-2.5 border-b border-divider px-3.5 py-[9px] text-[14.5px] font-semibold text-ink last:border-b-0 has-disabled:cursor-default"
          >
            <input
              type="checkbox"
              aria-label={item.label}
              checked={ticked}
              disabled={!editable}
              onChange={(event) =>
                pf.togglePermission(item, event.target.checked)
              }
              className="peer m-0 mt-0.5 size-4 shrink-0 accent-teal"
            />
            <span className="peer-disabled:text-slate">
              {item.label}
              {ticked && !inRole && <Tag tone="add">Added</Tag>}
              {!ticked && inRole && <Tag tone="remove">Removed</Tag>}
              {item.needs.length > 0 && (
                <small className="block text-[13px] font-medium text-slate">
                  {`Needs: ${item.needs.map(label).join(", ")}`}
                </small>
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
      <CardHeader
        title="Permissions"
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
        <div className="grid grid-cols-[repeat(auto-fit,minmax(270px,1fr))] items-start gap-3.5">
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
