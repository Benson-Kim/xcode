import { PinInput } from "../ui";

// What is wrong with a new PIN before it is sent, or null.
export function newPinProblem(newPin: string, repeatPin: string) {
  if (!/^\d{4}$/.test(newPin)) return "The PIN is 4 digits.";
  if (newPin !== repeatPin) return "The two PINs do not match.";
  return null;
}

const digitsOnly = (value: string) => value.replace(/\D/g, "");

// The new PIN typed twice, for a first sign in, a reset or an invitation.
export function NewPinFields({
  newPin,
  repeatPin,
  onNewPin,
  onRepeatPin,
}: {
  newPin: string;
  repeatPin: string;
  onNewPin: (value: string) => void;
  onRepeatPin: (value: string) => void;
}) {
  return (
    <>
      <div className="f">
        <label htmlFor="siNew">New PIN</label>
        <PinInput
          id="siNew"
          name="newPin"
          inputMode="numeric"
          maxLength={4}
          autoComplete="new-password"
          autoFocus
          value={newPin}
          onChange={(event) => onNewPin(digitsOnly(event.target.value))}
        />
      </div>
      <div className="f">
        <label htmlFor="siNew2">Repeat PIN</label>
        <PinInput
          id="siNew2"
          name="repeatPin"
          inputMode="numeric"
          maxLength={4}
          autoComplete="new-password"
          value={repeatPin}
          onChange={(event) => onRepeatPin(digitsOnly(event.target.value))}
        />
      </div>
    </>
  );
}
