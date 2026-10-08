import type { ReactNode } from "react";

import { formatPhone } from "@xcode/shared/format";

import type { Person, Role } from "../../lib/types";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  CurrencyInput,
  ErrorSummary,
  Field,
  FormActions,
  Grid2,
  Note,
  PageHeader,
  SelectInput,
  Skeleton,
  Spacer,
  TextInput,
} from "../ui";
import type { Errors, PersonForm } from "./model";

type FormProps = {
  form: PersonForm;
  setField: <K extends keyof PersonForm>(key: K, value: PersonForm[K]) => void;
  errors: Errors;
  editable: boolean;
};

export function PersonHeader({ person }: { person?: Person }) {
  return (
    <PageHeader
      title={person ? `${person.firstName} ${person.lastName}` : "Add person"}
      description={
        person
          ? `Mobile ${formatPhone(person.phoneNumber)}`
          : "They sign in with this mobile number and set their own PIN with an email code."
      }
    />
  );
}

export function PersonNotices({
  person,
  canManage,
  self,
  ownerLock,
  errorCount,
  saveError,
}: {
  person?: Person;
  canManage: boolean;
  self: boolean;
  ownerLock: boolean;
  errorCount: number;
  saveError: string;
}) {
  return (
    <>
      <ErrorSummary count={errorCount} />
      {saveError && <Banner>{saveError}</Banner>}
      {!canManage ? (
        <Note>You can view people but not change them.</Note>
      ) : self ? (
        <Note>
          This is you. Someone else who manages people changes your details and
          access.
        </Note>
      ) : ownerLock ? (
        <Note>Only the owner can change the owner&apos;s access.</Note>
      ) : null}
      {person && !person.active && (
        <Note>This person has no access. They cannot sign in.</Note>
      )}
    </>
  );
}

export function PersonDetailsCard({
  form,
  setField,
  errors,
  editable,
}: FormProps) {
  return (
    <Card density="form">
      <CardHeader title="Details" />
      <Grid2>
        <Field id="person-first" label="First name" error={errors.firstName}>
          <TextInput
            value={form.firstName}
            disabled={!editable}
            autoComplete="off"
            onChange={(event) => setField("firstName", event.target.value)}
          />
        </Field>
        <Field id="person-last" label="Last name" error={errors.lastName}>
          <TextInput
            value={form.lastName}
            disabled={!editable}
            autoComplete="off"
            onChange={(event) => setField("lastName", event.target.value)}
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
            onChange={(event) => setField("phoneNumber", event.target.value)}
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
            onChange={(event) => setField("email", event.target.value)}
          />
        </Field>
      </Grid2>
    </Card>
  );
}

export function PersonRoleCard({
  person,
  roles,
  assignable,
  selectedRole,
  error,
  editable,
  onChange,
}: {
  person?: Person;
  roles?: Role[];
  assignable: Role[];
  selectedRole: string;
  error?: string;
  editable: boolean;
  onChange: (role: string) => void;
}) {
  return (
    <Card density="form">
      <CardHeader
        title="Role"
        description="A starting set of permissions. You can change single permissions further down."
      />
      <Grid2 narrow>
        <Field
          id="person-role"
          label="Role"
          error={error}
          hint={
            person
              ? "Changing the role resets single permissions to the new role."
              : roles && !assignable.length
                ? "You cannot assign any available role."
                : undefined
          }
        >
          {!roles ? (
            <Skeleton className="h-12 rounded-[10px]" />
          ) : (
            <SelectInput
              value={selectedRole}
              disabled={!editable || !assignable.length}
              onChange={(event) => onChange(event.target.value)}
            >
              {assignable.map((role) => (
                <option key={role.id} value={role.name}>
                  {role.name}
                </option>
              ))}
            </SelectInput>
          )}
        </Field>
      </Grid2>
    </Card>
  );
}

export function ApprovalLimitCard({
  value,
  disabled,
  onChange,
}: {
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <Card density="form">
      <CardHeader
        title="Approval limit"
        description="The most they can approve in one entry."
      />
      <Grid2 narrow>
        <Field
          id="person-limit"
          label="Limit per entry"
          hint="Leave empty for no limit."
        >
          <CurrencyInput
            min="0"
            step="1"
            value={value}
            disabled={disabled}
            onChange={(event) => onChange(event.target.value)}
          />
        </Field>
      </Grid2>
    </Card>
  );
}

export function RemoveAccessCard({
  reason,
  error,
  onChange,
}: {
  reason: string;
  error: string;
  onChange: (value: string) => void;
}) {
  return (
    <Card density="form">
      <CardHeader
        title="Reason for removing access"
        description="A short reason is required and is kept in the change log."
      />
      <Field id="remove-reason" label="Reason">
        <TextInput
          autoFocus
          value={reason}
          maxLength={500}
          autoComplete="off"
          placeholder="For example, left the organization"
          aria-invalid={Boolean(error) || undefined}
          onChange={(event) => onChange(event.target.value)}
        />
      </Field>
      {error && <Banner>{error}</Banner>}
    </Card>
  );
}

type ActionsProps = {
  person?: Person;
  editable: boolean;
  busy: boolean;
  saveDisabled: boolean;
  confirmRemove: boolean;
  onSave: () => void;
  onClose: () => void;
  onLifecycle: (action: "activate" | "deactivate" | "sign-out") => void;
};

function LifecycleButtons({
  person,
  busy,
  confirmRemove,
  onLifecycle,
}: ActionsProps & { person: Person }): ReactNode {
  return (
    <>
      <Button
        tone="warn"
        disabled={busy}
        onClick={() => onLifecycle("sign-out")}
      >
        Sign out of all devices
      </Button>
      {person.active ? (
        <Button
          tone="danger"
          disabled={busy}
          onClick={() => onLifecycle("deactivate")}
        >
          {confirmRemove ? "Confirm removal" : "Remove access"}
        </Button>
      ) : (
        <Button
          tone="ok"
          disabled={busy}
          onClick={() => onLifecycle("activate")}
        >
          Give access back
        </Button>
      )}
    </>
  );
}

export function PersonActions(props: ActionsProps) {
  const { person, editable } = props;
  return (
    <FormActions>
      {editable && (
        <Button
          tone="ok"
          disabled={props.busy || props.saveDisabled}
          onClick={props.onSave}
        >
          {person ? "Save changes" : "Save person"}
        </Button>
      )}
      <Button tone="quiet" onClick={props.onClose}>
        {editable ? "Cancel" : "Back"}
      </Button>
      <Spacer />
      {editable && person && <LifecycleButtons {...props} person={person} />}
    </FormActions>
  );
}
