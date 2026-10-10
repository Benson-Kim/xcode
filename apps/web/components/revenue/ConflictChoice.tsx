import type { RevenueCell, SaveRevenue } from "@xcode/shared/revenue";

import { useFormats } from "../../lib/formats";
import { DialogFooter } from "../pettycash/DialogFooter";
import { Button, Hint, Note, Stat, StatGrid } from "../ui";
import { entryLabel } from "./capture";

// A save that met a newer record: keep what is saved or replace it with the person's entry.
export function ConflictChoice({
  message,
  current,
  mine,
  saving,
  onReplace,
  onKeep,
}: {
  message: string;
  current: RevenueCell;
  mine: SaveRevenue | string;
  saving: boolean;
  onReplace: () => void;
  onKeep: () => void;
}) {
  const formats = useFormats();
  return (
    <>
      <Note>{message}</Note>
      <StatGrid className="grid-cols-2">
        <Stat label="Saved value" value={entryLabel(formats, current)} />
        <Stat
          label="Yours"
          value={typeof mine === "string" ? "" : entryLabel(formats, mine)}
        />
      </StatGrid>
      {!current.canEdit && (
        <Hint>
          Your access does not include changing the saved record for this day.
        </Hint>
      )}
      <DialogFooter>
        <Button tone="outline" disabled={saving} onClick={onKeep}>
          Keep saved
        </Button>
        {current.canEdit && (
          <Button tone="ok" disabled={saving} onClick={onReplace}>
            {saving ? "Saving…" : "Replace with mine"}
          </Button>
        )}
      </DialogFooter>
    </>
  );
}
