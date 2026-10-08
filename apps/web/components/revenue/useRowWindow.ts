"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type RefObject,
} from "react";

const ROW_HEIGHT = 57;
const DETAIL_HEIGHT = 330;
const OVERSCAN = 8;
const FIRST_PAINT = 30;

// The items overlapping [from, to), with some to spare either side. `offsets` holds where each item starts, and the
// body's height last.
function near(offsets: readonly number[], from: number, to: number) {
  const count = offsets.length - 1;
  let start = 0;
  while (start < count && offsets[start + 1] <= from) start++;
  let end = start;
  while (end < count && offsets[end] < to) end++;
  return {
    start: Math.max(0, start - OVERSCAN),
    end: Math.min(count, end + OVERSCAN),
  };
}

// Which items of a long table body are near the screen as the page scrolls. Each item is one or more rows, keyed for
// measuring; a row not measured yet counts at an estimate. Rows outside the window are left out of the page, and
// `before`/`after` give the height their spacers stand in for. When off, every item is in the window.
export function useRowWindow(
  items: readonly (readonly string[])[],
  enabled: boolean,
  body: RefObject<HTMLElement | null>,
) {
  const [heights, setHeights] = useState<ReadonlyMap<string, number>>(
    () => new Map(),
  );
  const [range, setRange] = useState({ start: 0, end: FIRST_PAINT });

  const offsets = useMemo(() => {
    const at = [0];
    let offset = 0;
    for (const keys of items) {
      for (let index = 0; index < keys.length; index++)
        offset +=
          heights.get(keys[index]) ||
          (index === 0 ? ROW_HEIGHT : DETAIL_HEIGHT);
      at.push(offset);
    }
    return at;
  }, [items, heights]);

  useEffect(() => {
    if (!enabled) return;
    let frame = 0;
    const update = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const element = body.current;
        if (!element) return;
        const from = Math.max(0, -element.getBoundingClientRect().top);
        const next = near(offsets, from, from + window.innerHeight);
        setRange((current) =>
          current.start === next.start && current.end === next.end
            ? current
            : next,
        );
      });
    };
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [enabled, body, offsets]);

  // Rows report their height as they mount.
  const measure = useCallback((element: HTMLElement | null) => {
    const key = element?.dataset.measure;
    const height = element?.getBoundingClientRect().height;
    if (key && height)
      setHeights((current) =>
        current.get(key) === height
          ? current
          : new Map(current).set(key, height),
      );
  }, []);

  // Brings an item into the window and scrolls the page to it, for focus to go back to a row scrolled away.
  const reveal = useCallback(
    (index: number) => {
      const element = body.current;
      if (!element) return;
      const visible = Math.ceil(window.innerHeight / ROW_HEIGHT);
      setRange({
        start: Math.max(0, index - OVERSCAN),
        end: Math.min(offsets.length - 1, index + visible + OVERSCAN),
      });
      const page = document.scrollingElement ?? document.documentElement;
      page.scrollTop = Math.max(
        0,
        page.scrollTop +
          element.getBoundingClientRect().top +
          offsets[index] -
          window.innerHeight / 3,
      );
    },
    [body, offsets],
  );

  const total = offsets.length - 1;
  if (!enabled)
    return { start: 0, end: total, before: 0, after: 0, measure, reveal };
  const end = Math.min(range.end, total);
  const start = Math.min(range.start, end);
  return {
    start,
    end,
    before: offsets[start],
    after: offsets[total] - offsets[end],
    measure,
    reveal,
  };
}
