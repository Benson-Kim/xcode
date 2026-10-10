import { useSession } from "../../lib/session-context";
import type {
  PermissionGroup,
  Person,
  Role,
  ScopeOptions,
} from "../../lib/types";
import { PermissionsCard } from "./PermissionsCard";
import {
  ApprovalLimitCard,
  PersonActions,
  PersonDetailsCard,
  PersonHeader,
  PersonNotices,
  PersonRoleCard,
  RemoveAccessCard,
} from "./PersonCards";
import { ScopeCard } from "./ScopeCard";
import { usePersonActions } from "./usePersonActions";
import { usePersonForm } from "./usePersonForm";

type Props = {
  person?: Person;
  // Each arrives on its own request; until then its section shows placeholders.
  roles?: Role[];
  groups?: PermissionGroup[];
  scopeOptions?: ScopeOptions;
  canManage: boolean;
  canManageAccess: boolean;
  onClose: () => void;
  onSaved: () => void;
};

export function PersonEditor({
  person,
  roles,
  groups,
  scopeOptions,
  canManage,
  canManageAccess,
  onClose,
  onSaved,
}: Props) {
  const { session } = useSession();
  const pf = usePersonForm(person, roles, groups);
  const actions = usePersonActions({ person, onSaved });
  const { errors } = actions;
  const { form } = pf;

  const self = Boolean(person && person.id === session?.userId);
  const ownerLock = person?.role === "Owner" && session?.role !== "Owner";
  const editable = canManage && !self && !ownerLock;
  const permissionsEditable = editable && canManageAccess;
  const permissionsReady = Boolean(roles && groups);

  return (
    <section>
      <PersonHeader person={person} />
      <div className="flex flex-col gap-[22px] rounded-[18px] border border-line bg-surface p-[22px]">
        <PersonNotices
          person={person}
          canManage={canManage}
          self={self}
          ownerLock={ownerLock}
          errorCount={Object.keys(errors).length}
          saveError={actions.saveError}
        />
        <PersonDetailsCard
          form={form}
          setField={pf.setField}
          errors={errors}
          editable={editable}
        />
        <PersonRoleCard
          person={person}
          roles={roles}
          assignable={pf.assignable}
          selectedRole={pf.selectedRole}
          error={errors.role}
          editable={editable}
          onChange={pf.changeRole}
        />
        <ScopeCard
          form={form}
          setField={pf.setField}
          toggleScope={pf.toggleScope}
          scopeOptions={scopeOptions}
          selectedRole={pf.selectedRole}
          editable={editable}
          error={errors.scope}
        />
        <PermissionsCard
          groups={groups}
          pf={pf}
          ready={permissionsReady}
          editable={editable}
          canManageAccess={canManageAccess}
          error={errors.permissions}
        />
        {pf.needsLimit && (
          <ApprovalLimitCard
            value={form.approvalLimit}
            disabled={!permissionsEditable}
            onChange={(value) => pf.setField("approvalLimit", value)}
          />
        )}
        {actions.confirmRemove && person?.active && editable && (
          <RemoveAccessCard
            reason={actions.removeReason}
            error={actions.removeError}
            onChange={actions.changeRemoveReason}
          />
        )}
        <PersonActions
          person={person}
          editable={editable}
          busy={actions.busy}
          saveDisabled={!permissionsReady}
          confirmRemove={actions.confirmRemove}
          onSave={() => void actions.save(pf, Boolean(roles))}
          onClose={onClose}
          onLifecycle={(action) => void actions.lifecycle(action)}
        />
      </div>
    </section>
  );
}
