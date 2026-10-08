import { useLayoutEffect, useRef } from "react";

// The newest value of a prop or callback, readable from effects and timers without listing it as a dependency.
export function useLatest<T>(value: T) {
  const ref = useRef(value);
  useLayoutEffect(() => {
    ref.current = value;
  });
  return ref;
}
