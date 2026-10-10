import { useFormats } from "../../lib/formats";
import { recurringFrequency } from "../recurringPresentation";
import type { RecurringItem } from "../setup/shared";
import { Banner, ErrorSummary, Note } from "../ui";
import type { ItemStatus } from "./schedule";

type Props = {
  item?: RecurringItem;
  status: ItemStatus;
  today?: string;
  canEdit: boolean;
  errorCount: number;
  saveError: string;
  loadError?: string;
  legacyNeeds: unknown[];
};

export function RecurringNotices({
  item,
  status,
  today,
  canEdit,
  errorCount,
  saveError,
  loadError,
  legacyNeeds,
}: Props) {
  const { formatDateOnly } = useFormats();
  const { stopped, futureStop, startLocked } = status;
  return (
    <>
      <ErrorSummary count={errorCount} />
      {saveError && <Banner>{saveError}</Banner>}
      {loadError && <Banner>{loadError}</Banner>}
      {!canEdit &&
        (item?.partial ? (
          <Note>
            This item also posts to vehicles you can&apos;t see, so only someone
            who can see all of them can change it. The amounts here are your
            vehicles&apos; share.
          </Note>
        ) : (
          <Note>You can view this item but not change it.</Note>
        ))}
      {item && startLocked && !stopped && today && (
        <Note tone="info">
          Changes apply from {formatDateOnly(today)}. Postings before that stay
          as they were.
        </Note>
      )}
      {stopped && (
        <Note>
          Stopped. The last posting was on or before{" "}
          {formatDateOnly(item!.stoppedFrom!)}.
        </Note>
      )}
      {futureStop && (
        <Note tone="info">
          Scheduled to stop on {formatDateOnly(futureStop)}. You can still
          change the schedule, or cancel the stop, before then.
        </Note>
      )}
      {legacyNeeds.length > 0 && !stopped && (
        <Note tone="info">
          Saved before the rules it would follow today, and still posting as it
          is.
          {canEdit
            ? ` To save a change, choose ${legacyNeeds.join(" and ")}.`
            : ""}
        </Note>
      )}
    </>
  );
}

// An item someone can change is titled for the change, with its name under it; one they can only view, by its name.
export function recurringHeading(
  item?: RecurringItem,
  kind?: number,
  canEdit = true,
) {
  const editTitle = item?.kind === 2 ? "Edit saving" : "Edit scheduled expense";
  return {
    title: item
      ? canEdit
        ? editTitle
        : item.name
      : kind === 2
        ? "New saving"
        : "New scheduled expense",
    description: item
      ? `${canEdit ? `${item.name} · ` : ""}${recurringFrequency(item)}${item.note ? `. ${item.note}` : ""}`
      : "It posts to the vehicles you choose on every due date.",
  };
}
