"use client";

import { PIN_HELP, validatePin } from "@xcode/shared";

export function PinInput({
  value,
  onChange,
  newPin = false,
}: {
  value: string;
  onChange: (value: string) => void;
  newPin?: boolean;
}) {
  const error = newPin && value.length > 0 ? validatePin(value) : null;

  return (
    <div className="space-y-2">
      <label htmlFor="pin" className="block font-medium">
        {newPin ? "New PIN" : "PIN"}
      </label>
      <input
        id="pin"
        name="pin"
        type="password"
        inputMode="numeric"
        pattern="[0-9]{4,8}"
        minLength={4}
        maxLength={8}
        autoComplete={newPin ? "new-password" : "current-password"}
        required
        value={value}
        onChange={(event) =>
          onChange(event.target.value.replace(/[^0-9]/g, ""))
        }
        aria-invalid={Boolean(error)}
        aria-describedby={newPin ? "pin-help" : undefined}
      />
      {newPin && (
        <p
          id="pin-help"
          className={error ? "text-sm text-red-700" : "text-sm text-slate-600"}
        >
          {PIN_HELP}
        </p>
      )}
    </div>
  );
}
