"use client";

import { useState } from "react";

import { PIN_HELP, validatePin } from "@xcode/shared/auth";

import { AlertIcon, Field, LinkButton, TextInput } from "./ui";

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
    <Field
      label={newPin ? "New PIN" : "PIN"}
      id="pin"
      action={
        !newPin && (
          <LinkButton
            align="end"
            compact
            aria-controls="pin"
            aria-pressed={visible}
            onClick={() => setVisible((current) => !current)}
          >
            {visible ? "Hide" : "Show"}
          </LinkButton>
        )
      }
    >
      <TextInput
        className="text-[22px] tracking-[0.4em] placeholder:text-[17px] placeholder:tracking-normal"
        id="pin"
        name="pin"
        type={visible ? "text" : "password"}
        inputMode="numeric"
        pattern="[0-9]{4,8}"
        minLength={4}
        maxLength={8}
        placeholder="4 to 8 numbers"
        autoComplete={newPin ? "new-password" : "current-password"}
        required
        value={value}
        onChange={(event) =>
          onChange(event.target.value.replace(/[^0-9]/g, ""))
        }
        aria-invalid={Boolean(error)}
        aria-describedby={error ? "pin-help" : undefined}
      />
      {error && (
        <p
          id="pin-help"
          className="m-0 flex items-start gap-1.5 text-[13px] font-semibold text-clay"
        >
          <AlertIcon className="mt-px shrink-0" />
          {PIN_HELP}
        </p>
      )}
    </Field>
  );
}
