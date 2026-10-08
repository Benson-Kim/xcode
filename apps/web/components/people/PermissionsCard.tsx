import { plural } from "@xcode/shared/format";

import type { PermissionGroup } from "../../lib/types";
import {
  Card,
  CardHeader,
  Chip,
  ChipGroup,
  Choice,
  ErrorText,
  ListSkeleton,
  Note,
  Tag,
} from "../ui";
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
    <div className="border-t border-divider pt-3">
      <h3 className="m-0 mb-1 flex justify-between gap-2 text-[15px] font-bold">
        {group.name}
        <small className="text-[13px] font-medium text-grey">
          {group.items.filter((item) => permissions.includes(item.key)).length}{" "}
          of {group.items.length}
        </small>
      </h3>
      {/* Side by side on wide screens, as in the design's permissions panel (.pg-list). */}
      <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-x-6 max-[720px]:grid-cols-1">
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
                  {!ticked && inRole && <Tag tone="remove">Removed</Tag>}
                </>
              }
              aria-label={item.label}
              description={
                item.needs.length
                  ? `Needs: ${item.needs.map(label).join(", ")}`
                  : undefined
              }
              checked={ticked}
              disabled={!editable}
              onChange={(event) =>
                pf.togglePermission(item, event.target.checked)
              }
            />
          );
        })}
      </div>
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
    <Card density="form">
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
      {ready &&
        groups!.map((group) => (
          <PermissionGroupList
            key={group.name}
            group={group}
            pf={pf}
            editable={permissionsEditable}
          />
        ))}
      {error && <ErrorText>{error}</ErrorText>}
    </Card>
  );
}
