"use client";

import type { ComponentProps } from "react";

import { useFormats } from "../../lib/formats";
import { TextInput } from "../ui";

// An amount with its currency in front. It keeps what is typed, minus sign included, so money coming back can be
// entered; parsePettyCashAmount decides whether it is valid.
export function AmountInput(
  props: Omit<ComponentProps<"input">, "type" | "inputMode">,
) {
  const { currencyCode } = useFormats();
  return (
    <div className="flex w-full min-w-0 items-stretch">
      <span className="flex shrink-0 items-center rounded-l-[10px] border border-r-0 border-line bg-paper px-3 text-[15px] text-grey">
        {currencyCode()}
      </span>
      <TextInput
        {...props}
        inputMode="text"
        autoComplete="off"
        spellCheck={false}
        className="min-w-0 flex-1 rounded-l-none tabular-nums"
      />
    </div>
  );
}
