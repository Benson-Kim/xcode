"use client";

import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useState,
  type ComponentProps,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";

import { Dialog } from "../ui";

type Slot = { target: HTMLElement | null; claim: (on: boolean) => void };
const SlotContext = createContext<Slot | null>(null);

// A pop up whose actions come from the form in its body: a DialogFooter anywhere inside lands in the dialog's own
// action bar (.mf), which shows only while one is there.
export function FormDialog({
  children,
  ...props
}: Omit<ComponentProps<typeof Dialog>, "footer">) {
  const [target, setTarget] = useState<HTMLElement | null>(null);
  const [claims, setClaims] = useState(0);
  const claim = useCallback(
    (on: boolean) => setClaims((count) => count + (on ? 1 : -1)),
    [],
  );
  const slot = useMemo(() => ({ target, claim }), [target, claim]);
  return (
    <Dialog
      {...props}
      footer={
        claims > 0 ? <span ref={setTarget} className="contents" /> : undefined
      }
    >
      <SlotContext.Provider value={slot}>{children}</SlotContext.Provider>
    </Dialog>
  );
}

// The actions of a form in a FormDialog. A submit button outside the form joins it with form="<the form's id>".
export function DialogFooter({ children }: { children: ReactNode }) {
  const slot = useContext(SlotContext);
  const claim = slot?.claim;
  useLayoutEffect(() => {
    if (!claim) return;
    claim(true);
    return () => claim(false);
  }, [claim]);
  return slot?.target ? createPortal(children, slot.target) : null;
}
