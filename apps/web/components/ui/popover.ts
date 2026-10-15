import { useEffect, useLayoutEffect, type RefObject } from "react";

// While open, a press outside the element (and the pop over it opened, which may sit elsewhere in the page) or the
// Escape key closes it. onClose says whether focus should go back to the control that opened it: it should after
// Escape, but not after a press that is moving focus elsewhere.
export function useDismiss(
  open: boolean,
  ref: RefObject<HTMLElement | null>,
  onClose: (returnFocus: boolean) => void,
  floating?: RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    if (!open) return;
    const outside = (event: Event) => {
      const target = event.target as Node;
      if (floating?.current?.contains(target)) return;
      if (ref.current && !ref.current.contains(target)) onClose(false);
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
  }, [open, ref, onClose, floating]);
}

// Where a pop over is drawn: the open pop up that holds the control, else the app's frame (.main) beside the working
// area, as the design's #pop is, so the headline band's and the date control's styles never reach into it.
export function popLayer(control: Element): HTMLElement {
  return (
    control.closest<HTMLElement>("dialog[open]") ??
    document.querySelector<HTMLElement>(".main") ??
    document.body
  );
}

// Places a pop over (.pop, a list) under the control that opened it, as the design's openPop does: lined up with the
// control's left edge ("start") or right edge ("end"), kept 8px inside the window. It is fixed to the window and drawn
// above the rows and cards around it, so no table, card or headline band can clip it or be pushed down by it. When
// there is more room above the control than below, it opens upwards, anchored by its bottom edge so that a list that
// shrinks as you type stays against the control. It follows the control on scroll and resize.
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
      const style = box.style;
      // Out of the flow before measuring, so a list that opened inside the control's box does not stretch it.
      style.setProperty("position", "fixed");
      const rect = from.getBoundingClientRect();
      if (matchWidth) style.setProperty("width", `${Math.round(rect.width)}px`);
      const width = box.offsetWidth;
      const left = align === "start" ? rect.left : rect.right - width;
      const below = window.innerHeight - rect.bottom - gap - 8;
      const above = rect.top - gap - 8;
      const upwards = box.offsetHeight > below && above > below;
      style.setProperty("z-index", "50");
      style.setProperty("margin", "0");
      style.setProperty(
        "left",
        `${Math.round(Math.max(8, Math.min(left, window.innerWidth - width - 8)))}px`,
      );
      style.setProperty(
        "top",
        upwards ? "auto" : `${Math.round(rect.bottom + gap)}px`,
      );
      style.setProperty(
        "bottom",
        upwards
          ? `${Math.round(window.innerHeight - rect.top + gap)}px`
          : "auto",
      );
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
