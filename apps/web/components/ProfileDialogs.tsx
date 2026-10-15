"use client";

import { useId, useState } from "react";

import { AuthError, type TrustedDevice } from "@xcode/shared/auth";

import { authApi } from "../lib/api";
import { useFormats } from "../lib/formats";
import { useSession } from "../lib/session-context";
import { Banner, Button, Dialog, ListSkeleton, useToast } from "./ui";

// "Change PIN" from the profile menu: the current PIN, the new one and it again. The same PIN rules as sign in.
export function ChangePinDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const toast = useToast();
  const formId = useId();
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const digits = (value: string) => value.replace(/\D/g, "");

  function close() {
    setCurrent("");
    setNext("");
    setRepeat("");
    setError("");
    onClose();
  }

  async function save() {
    if (!/^\d{4}$/.test(current)) return setError("Enter your current PIN.");
    if (!/^\d{4}$/.test(next)) return setError("The PIN is 4 digits.");
    if (next !== repeat) return setError("The two PINs do not match.");
    setBusy(true);
    setError("");
    try {
      await authApi("pin/change", { currentPin: current, newPin: next });
      toast("PIN changed");
      close();
    } catch (failure) {
      setError(
        failure instanceof AuthError
          ? failure.response.status === "authentication_failed"
            ? "The current PIN is not right."
            : failure.response.status === "invalid_pin" &&
                failure.response.pinProblem === "unchanged"
              ? "Choose a PIN different from the current one."
              : failure.message
          : "Could not reach the service. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const field = (
    id: string,
    label: string,
    value: string,
    set: (value: string) => void,
    autoComplete: string,
  ) => (
    <div className="f">
      <label htmlFor={id}>{label}</label>
      <input
        className="inp num pinin"
        id={id}
        type="password"
        inputMode="numeric"
        maxLength={4}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => set(digits(event.target.value))}
      />
    </div>
  );

  return (
    <Dialog
      open={open}
      size="sm"
      title="Change PIN"
      onClose={close}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={close}>
            Cancel
          </Button>
          <Button tone="ok" type="submit" form={formId} disabled={busy}>
            Save PIN
          </Button>
        </>
      }
    >
      <form
        id={formId}
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        {field("dOld", "Current PIN", current, setCurrent, "current-password")}
        {field("dNew", "New PIN", next, setNext, "new-password")}
        {field("dNew2", "Repeat PIN", repeat, setRepeat, "new-password")}
        {error && <div className="ferr">{error}</div>}
      </form>
    </Dialog>
  );
}

// The person's trusted devices, with "This device" marked and Remove on each. Removing this device signs it out.
export function DeviceTable({
  devices,
  onRemove,
  busy,
}: {
  devices: TrustedDevice[];
  onRemove?: (device: TrustedDevice) => void;
  busy?: boolean;
}) {
  const { formatDateOnly, formatDateTime } = useFormats();
  if (!devices.length) return <div className="muted">No trusted device</div>;
  return (
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
            {devices.map((device) => (
              <tr key={device.id}>
                <td className="item">
                  {device.name || "Unnamed device"}
                  {device.thisDevice && (
                    <>
                      {" "}
                      <span className="chip mute">This device</span>
                    </>
                  )}
                </td>
                <td className="nw">
                  {formatDateOnly(device.trustedAt.slice(0, 10))}
                </td>
                <td className="nw">
                  {device.lastUsedAt ? formatDateTime(device.lastUsedAt) : ""}
                </td>
                <td className="r">
                  {onRemove && (
                    <button
                      type="button"
                      className="act bad"
                      disabled={busy}
                      aria-label={`Remove ${device.name || "this device"}`}
                      onClick={() => onRemove(device)}
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
  );
}

export function TrustedDevicesDialog({
  open,
  devices,
  loading,
  error,
  onChanged,
  onClose,
  onSignedOut,
}: {
  open: boolean;
  devices: TrustedDevice[] | undefined;
  loading: boolean;
  error: string;
  onChanged: () => void;
  onClose: () => void;
  onSignedOut: () => void;
}) {
  const { session } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");

  async function remove(device: TrustedDevice) {
    setBusy(true);
    setFailure("");
    try {
      await authApi(`trusted-devices/${device.id}/remove`, {
        thisDevice: device.thisDevice,
      });
      toast("Removed");
      if (device.thisDevice) onSignedOut();
      else onChanged();
    } catch (reason) {
      setFailure(
        reason instanceof Error
          ? reason.message
          : "The device could not be removed.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      size="md"
      title="Trusted devices"
      subtitle={
        session ? `${session.firstName} ${session.lastName}`.trim() : ""
      }
      onClose={onClose}
      footer={
        <Button tone="outline" onClick={onClose}>
          Close
        </Button>
      }
    >
      {(error || failure) && <Banner>{failure || error}</Banner>}
      {loading && !devices ? (
        <ListSkeleton rows={2} />
      ) : (
        <DeviceTable devices={devices ?? []} busy={busy} onRemove={remove} />
      )}
    </Dialog>
  );
}
