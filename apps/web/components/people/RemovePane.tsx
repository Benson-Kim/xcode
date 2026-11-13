import type { Person } from "../../lib/types";
import { Button } from "../ui";
import { personStatus } from "./model";

export type RemovalAction = "block" | "erase" | "delete";

// The "Block or delete" pane: the three ways to take someone out, side by side with what each one does, so the
// reversible one is the first found. Each opens its own confirmation.
export function RemovePane({
  person,
  rights,
  onAction,
}: {
  person: Person;
  rights: { block: boolean; erase: boolean; remove: boolean };
  onAction: (action: RemovalAction) => void;
}) {
  const first = person.firstName;
  const blocked = personStatus(person) === "blocked";
  return (
    <>
      {rights.block && (
        <div className="pblock">
          <div className="pbh">
            <b>{blocked ? "Unblock" : "Block"}</b>
            {blocked && <span className="chip bad">Blocked</span>}
          </div>
          <p className="muted">
            {blocked
              ? `${first} can sign in again with a new invitation or PIN reset. Their records are unchanged.`
              : `${first} stops signing in at once and their trusted devices are removed. Their records stay, and you can unblock them later.`}
          </p>
          <div>
            <Button
              tone={blocked ? "ok" : "danger"}
              onClick={() => onAction("block")}
            >
              {blocked ? `Unblock ${first}` : `Block ${first}`}
            </Button>
          </div>
        </div>
      )}
      {rights.block && (
        <div className="pblock">
          <div className="pbh">
            <b>Erase personal details</b>
          </div>
          <p className="muted">
            Erases their name, email address and mobile number for good. Money
            records stay, shown as Former member.{" "}
            {rights.erase ? "" : `Block ${first} first.`}
          </p>
          <div>
            <Button
              tone="danger"
              disabled={!rights.erase}
              onClick={() => onAction("erase")}
            >
              Erase {first}
            </Button>
          </div>
        </div>
      )}
      {rights.remove && (
        <div className="pblock">
          <div className="pbh">
            <b>Delete</b>
          </div>
          <p className="muted">
            Deletes {first} permanently and removes them from this organization.
            Only possible while they have no records; once they have recorded
            anything, block them instead.
          </p>
          <div>
            <Button tone="danger" onClick={() => onAction("delete")}>
              Delete {first}
            </Button>
          </div>
        </div>
      )}
    </>
  );
}
