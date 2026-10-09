import { useEffect, type RefObject } from "react";

// While open, a press outside the element or the Escape key closes it. onClose says whether focus should go back to
// the control that opened it: it should after Escape, but not after a press that is moving focus elsewhere.
export function useDismiss(
  open: boolean,
  ref: RefObject<HTMLElement | null>,
  onClose: (returnFocus: boolean) => void,
) {
  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      if (ref.current && !ref.current.contains(event.target as Node))
        onClose(false);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose(true);
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("touchstart", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("touchstart", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open, ref, onClose]);
}
