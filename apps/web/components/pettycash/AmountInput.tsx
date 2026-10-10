"use client";

import type { ComponentProps } from "react";

import { TextInput } from "../ui";

// An amount; its label names the currency ("Unit cost, KES"), as in the design. It keeps what is typed, minus sign
// included, so money coming back can be entered; parsePettyCashAmount decides whether it is valid.
export function AmountInput(
  props: Omit<ComponentProps<"input">, "type" | "inputMode">,
) {
  return (
    <TextInput
      {...props}
      inputMode="text"
      autoComplete="off"
      spellCheck={false}
    />
  );
}
