"use client";

import { useState, type ComponentProps } from "react";

import { cn } from "./cn";
import { EyeIcon, EyeOffIcon } from "./icons";

// A PIN field with a show/hide button inside it. The button keeps the typing in the field: a press does not take
// focus from it, and it never submits the form.
export function PinInput({
  className,
  ...props
}: Omit<ComponentProps<"input">, "type">) {
  const [shown, setShown] = useState(false);
  return (
    <div className="pinw">
      <input
        {...props}
        className={cn("inp num pinin", className)}
        type={shown ? "text" : "password"}
      />
      <button
        type="button"
        className="pineye"
        aria-label={shown ? "Hide PIN" : "Show PIN"}
        aria-pressed={shown}
        aria-controls={props.id}
        disabled={props.disabled}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => setShown((value) => !value)}
      >
        {shown ? <EyeOffIcon /> : <EyeIcon />}
      </button>
    </div>
  );
}
