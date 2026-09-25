"use client";

import { useState } from "react";
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
  const [visible, setVisible] = useState(false);
  const error = newPin && value.length > 0 ? validatePin(value) : null;

  return (
    <div className="field">
      <div className="field-head">
        <label htmlFor="pin">
        {newPin ? "New PIN" : "PIN"}
        </label>
        {!newPin && (
          <button
            type="button"
            className="link-button"
            aria-controls="pin"
            aria-pressed={visible}
            onClick={() => setVisible((current) => !current)}
          >
            {visible ? "Hide" : "Show"}
          </button>
        )}
      </div>
      <input
        className="input digits"
        id="pin"
        name="pin"
        type={visible ? "text" : "password"}
        inputMode="numeric"
        pattern="[0-9]{4}"
        minLength={4}
        maxLength={4}
        autoComplete={newPin ? "new-password" : "current-password"}
        required
        value={value}
        onChange={(event) =>
          onChange(event.target.value.replace(/[^0-9]/g, ""))
        }
        aria-invalid={Boolean(error)}
        aria-describedby={newPin ? "pin-help" : undefined}
      />
      {newPin && error && <p id="pin-help" className="field-error">{PIN_HELP}</p>}
    </div>
  );
}
