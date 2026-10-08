import { ApiError } from "./request";

const DELAYS = [1000, 3000];

function transient(error: unknown) {
  return (
    error instanceof TypeError ||
    (error instanceof ApiError && (error.status === 503 || error.status === 0))
  );
}

function wait(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    if (signal.aborted) return reject(signal.reason);
    const onAbort = () => {
      clearTimeout(timer);
      reject(signal.reason);
    };
    const timer = setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export async function withRetry<T>(
  run: () => Promise<T>,
  signal: AbortSignal,
): Promise<T> {
  for (let attempt = 0; ; attempt++) {
    try {
      return await run();
    } catch (error) {
      if (signal.aborted || attempt >= DELAYS.length || !transient(error))
        throw error;
      await wait(DELAYS[attempt], signal);
    }
  }
}
