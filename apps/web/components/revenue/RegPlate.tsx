export { RegPlate } from "../ui";

export function BandSkeleton() {
  return (
    <span
      aria-hidden="true"
      className="block h-10 w-48 rounded-lg bg-glass-2 motion-safe:animate-pulse"
    />
  );
}
