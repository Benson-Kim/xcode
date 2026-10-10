import type { ComponentProps, ReactNode } from "react";

import type { Person, Role } from "../../lib/types";
import {
  Banner,
  Button,
  CurrencyInput,
  ErrorSummary,
  Field,
  Note,
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

export function FormSection(props: ComponentProps<"section">) {
  return <section {...props} className="f" />;
}

// A section title inside the person pop up (.flab), with its explanation under it.
export function SectionLabel({
  title,
  description,
}: {
  title: string;
  description?: ReactNode;
}) {
  return (
    <>
      <h3 className="flab">{title}</h3>
      {description && <div className="hint">{description}</div>}
    </>
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
    <>
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
        label="Email for codes"
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
    </>
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
    <Field
      id="person-role"
      label="Role"
      error={error}
      hint={
        person
          ? "Changing the role resets single permissions to the new role."
          : roles && !assignable.length
            ? "You cannot assign any available role."
            : "A starting set of permissions. You can change single permissions under Access."
      }
    >
      {!roles ? (
        <Skeleton className="h-11" />
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
    <Field
      id="person-limit"
      label="Limit per entry"
      hint="The most they can approve in one entry. Leave empty for no limit."
    >
      <CurrencyInput
        min="0"
        step="1"
        value={value}
        disabled={disabled}
        onChange={(event) => onChange(event.target.value)}
      />
    </Field>
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
    <FormSection>
      <SectionLabel
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
    </FormSection>
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

// The pop up's footer (.mf): what changes the person's access on the left, then Cancel and Save.
export function PersonActions(props: ActionsProps) {
  const { person, editable } = props;
  return (
    <>
      {editable && person && <LifecycleButtons {...props} person={person} />}
      <Spacer />
      <Button tone="outline" onClick={props.onClose}>
        {editable ? "Cancel" : "Close"}
      </Button>
      {editable && (
        <Button
          tone="ok"
          disabled={props.busy || props.saveDisabled}
          onClick={props.onSave}
        >
          Save
        </Button>
      )}
    </>
  );
}
