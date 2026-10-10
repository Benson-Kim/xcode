import { useEffect, useLayoutEffect, type RefObject } from "react";

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

// Places a pop over (.pop, a list) under the control that opened it, as the design's openPop does: lined up with the
// control's left edge ("start") or right edge ("end"), kept 8px inside the window. It is fixed to the window so the
// headline card, which clips what spills out of it, cannot cut it off; it follows the control on scroll and resize.
export function useAnchoredPosition(
  open: boolean,
  anchor: RefObject<HTMLElement | null>,
  floating: RefObject<HTMLElement | null>,
  { align = "start", gap = 8, matchWidth = false } = {} as {
    align?: "start" | "end";
    gap?: number;
    matchWidth?: boolean;
  },
) {
  useLayoutEffect(() => {
    if (!open) return;
    const place = () => {
      const from = anchor.current;
      const box = floating.current;
      if (!from || !box) return;
      const rect = from.getBoundingClientRect();
      const style = box.style;
      if (matchWidth) style.setProperty("width", `${Math.round(rect.width)}px`);
      const width = box.offsetWidth;
      const left = align === "start" ? rect.left : rect.right - width;
      style.setProperty("position", "fixed");
      style.setProperty(
        "left",
        `${Math.round(Math.max(8, Math.min(left, window.innerWidth - width - 8)))}px`,
      );
      style.setProperty("top", `${Math.round(rect.bottom + gap)}px`);
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor, floating, align, gap, matchWidth]);
}
