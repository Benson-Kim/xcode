"use client";

export default function PageError({
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <main style={{ padding: "2rem", textAlign: "center" }}>
      <h1>This page ran into a problem</h1>
      <button type="button" onClick={() => reset()}>
        Try again
      </button>
    </main>
  );
}
