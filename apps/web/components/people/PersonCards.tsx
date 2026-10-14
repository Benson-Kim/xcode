import type { Role } from "../../lib/types";
import { CurrencyInput, Skeleton } from "../ui";
import type { Errors, PersonForm } from "./model";
import type { PersonFormState } from "./usePersonForm";

// The Details pane of the person pop up (v2.32): names, job, mobile number, email for codes, and the petty cash
// float. No helper sentences.
export function DetailsPane({
  pf,
  roles,
  errors,
  editable,
  limitEditable,
}: {
  pf: PersonFormState;
  roles?: Role[];
  errors: Errors;
  editable: boolean;
  limitEditable: boolean;
}) {
  const { form, setField } = pf;
  const text = (
    id: string,
    label: string,
    key: keyof PersonForm & string,
    extra: Record<string, unknown> = {},
  ) => (
    <div className="f">
      <label htmlFor={id}>{label}</label>
      <input
        className="inp"
        id={id}
        value={String(form[key])}
        disabled={!editable}
        autoComplete="off"
        aria-invalid={errors[key as keyof Errors] ? true : undefined}
        onChange={(event) =>
          setField(key, event.target.value as PersonForm[typeof key])
        }
        {...extra}
      />
    </div>
  );
  return (
    <>
      <div className="fgrid">
        {text("pFirst", "First name", "firstName")}
        {text("pLast", "Last name", "lastName")}
        <div className="f">
          <label htmlFor="pTitle">Job</label>
          {!roles ? (
            <Skeleton className="h-11" />
          ) : (
            <select
              className="inp"
              id="pTitle"
              value={pf.selectedRole}
              disabled={!editable || !pf.assignable.length}
              aria-invalid={errors.role ? true : undefined}
              onChange={(event) => pf.changeRole(event.target.value)}
            >
              {pf.assignable.map((role) => (
                <option key={role.id} value={role.name}>
                  {role.name}
                </option>
              ))}
            </select>
          )}
        </div>
        {text("pPhone", "Mobile number", "phoneNumber", {
          className: "inp num",
          inputMode: "tel",
        })}
        {text("pEmail", "Email for codes", "email", {
          type: "email",
          autoCapitalize: "none",
          spellCheck: false,
        })}
      </div>
      <div className="pblock">
        <div className="pbh">
          <b>Petty cash</b>
        </div>
        <div className="checks">
          <label className="ck">
            <input
              type="checkbox"
              id="pFloat"
              checked={pf.holdsFloat}
              disabled={!limitEditable}
              onChange={(event) => pf.setFloat(event.target.checked)}
            />
            Holds a float
          </label>
        </div>
        {pf.needsLimit && (
          <div className="f">
            <label htmlFor="pLimit">Approval limit per entry, KES</label>
            <CurrencyInput
              id="pLimit"
              min="0"
              step="1"
              value={form.approvalLimit}
              disabled={!limitEditable}
              onChange={(event) =>
                setField("approvalLimit", event.target.value)
              }
            />
          </div>
        )}
      </div>
    </>
  );
}
