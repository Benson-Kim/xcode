"use client";

import { useLayoutEffect, useRef } from "react";

import { Banner, Button, Dialog, LoadingRegion, Skeleton } from "../ui";
import type { useSummaryImage } from "./useSummaryImage";

// The pop up of the Summary image: the picture as it will be saved, then Cancel or Save image.
export function SummaryImageDialog({
  image,
}: {
  image: ReturnType<typeof useSummaryImage>;
}) {
  const { shown, saving, error } = image;
  const frame = useRef<HTMLDivElement>(null);
  const canvas = shown?.canvas ?? null;
  const label = shown ? `${shown.layout.title}, ${shown.layout.subtitle}` : "";

  useLayoutEffect(() => {
    const host = frame.current;
    if (!host || !canvas) return;
    host.replaceChildren(canvas);
    return () => host.replaceChildren();
  }, [canvas]);

  return (
    <Dialog
      open={shown !== null}
      size="md"
      title="Summary image"
      subtitle={shown?.layout.period}
      busy={saving}
      onClose={image.close}
      footer={
        <>
          <Button tone="outline" disabled={saving} onClick={image.close}>
            Cancel
          </Button>
          <Button
            tone="primary"
            disabled={!canvas || saving}
            aria-busy={saving || undefined}
            onClick={() => void image.save()}
          >
            Save image
          </Button>
        </>
      }
    >
      {error && <Banner>{error}</Banner>}
      {canvas ? (
        <div
          ref={frame}
          role="img"
          aria-label={label}
          className="[&>canvas]:block [&>canvas]:h-auto [&>canvas]:w-full [&>canvas]:rounded-[10px] [&>canvas]:border [&>canvas]:border-line"
        />
      ) : (
        !error && (
          <LoadingRegion label="Drawing the image">
            <Skeleton className="h-72 w-full" />
          </LoadingRegion>
        )
      )}
    </Dialog>
  );
}
