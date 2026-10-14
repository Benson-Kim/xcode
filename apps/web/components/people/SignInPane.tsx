import { useFormats } from "../../lib/formats";
import type { Person, PersonSignIn } from "../../lib/types";
import { ListSkeleton } from "../ui";
import { STATUS_CHIPS } from "./model";

// The "Sign in" pane (v2.33): PIN status, last sign in, where codes go, and the trusted devices. With the right
// `people.sign_in`: make the person reset the PIN, remove a device, remove all. These act at once and are logged.
export function SignInPane({
  person,
  signIn,
  loading,
  canAct,
  busy,
  onPinReset,
  onRemoveDevice,
  onRemoveAll,
}: {
  person?: Person;
  signIn?: PersonSignIn;
  loading: boolean;
  canAct: boolean;
  busy: boolean;
  onPinReset: () => void;
  onRemoveDevice: (deviceId: string) => void;
  onRemoveAll: () => void;
}) {
  const { formatDateOnly, formatDateTime } = useFormats();
  if (!person)
    return (
      <div className="pblock">
        <div className="pbh">
          <b>PIN</b>
          <span className="chip wait">Not signed in yet</span>
        </div>
      </div>
    );
  if (!signIn)
    return loading ? (
      <div role="status" aria-busy="true">
        <span className="sr-only">Loading the sign in</span>
        <ListSkeleton rows={3} />
      </div>
    ) : null;
  const chip = STATUS_CHIPS[signIn.status] ?? STATUS_CHIPS.active;
  const canReset =
    canAct &&
    signIn.status !== "not_signed_in" &&
    signIn.status !== "pin_reset_due";
  return (
    <>
      <div className="pblock">
        <div className="pbh">
          <b>PIN</b>
          <span className={`chip ${chip.tone}`}>{chip.label}</span>
        </div>
        <div className="kvs">
          <div>
            <span>Last sign in</span>
            <b>
              {signIn.lastSignedInAt
                ? formatDateTime(signIn.lastSignedInAt)
                : "Never"}
            </b>
          </div>
          <div>
            <span>Codes go to</span>
            <b>{signIn.email}</b>
          </div>
        </div>
        {canReset && (
          <div>
            <button
              type="button"
              className="btn"
              disabled={busy}
              onClick={onPinReset}
            >
              Make {person.firstName} reset the PIN
            </button>
          </div>
        )}
      </div>
      <div className="pblock">
        <div className="pbh">
          <b>Trusted devices</b>
          {canAct && signIn.devices.length > 1 && (
            <button
              type="button"
              className="mlink"
              disabled={busy}
              onClick={onRemoveAll}
            >
              Remove all
            </button>
          )}
        </div>
        {signIn.devices.length === 0 ? (
          <div className="muted">No trusted device</div>
        ) : (
          <div className="tbl">
            <div className="scroll">
              <table className="tgh">
                <thead>
                  <tr>
                    <th>Device</th>
                    <th>Trusted on</th>
                    <th>Last used</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {signIn.devices.map((device) => (
                    <tr key={device.id}>
                      <td className="item">
                        {device.name || "Unnamed device"}
                      </td>
                      <td className="nw">
                        {formatDateOnly(device.trustedAt.slice(0, 10))}
                      </td>
                      <td className="nw">
                        {device.lastUsedAt
                          ? formatDateTime(device.lastUsedAt)
                          : ""}
                      </td>
                      <td className="r">
                        {canAct && (
                          <button
                            type="button"
                            className="act bad"
                            disabled={busy}
                            aria-label={`Remove ${device.name || "device"}`}
                            onClick={() => onRemoveDevice(device.id)}
                          >
                            Remove
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
