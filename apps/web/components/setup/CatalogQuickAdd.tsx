"use client";

import { streamError, useStreamedList } from "../../lib/data";
import {
  EXPENSE_CATEGORIES_PATH,
  EXPENSE_MAIN_CATEGORIES_PATH,
} from "../../lib/endpoints/catalog";
import type { ExpenseCategory, ExpenseMainCategory } from "../../lib/types";
import { CatalogDialog } from "./CatalogDialog";
import { useCatalogEditor, useCatalogRights } from "./useCatalogEditor";

export type AddedItem = { id: string; name: string; categoryName: string };

const byName = (left: { name: string }, right: { name: string }) =>
  left.name.localeCompare(right.name);

// The catalog's new item pop up, opened from another form's item list with what was typed there. Saving hands the
// new item back; cancelling closes it and leaves that form as it was. Only categories in use are offered: an item
// put in a stopped one is not offered to entries.
export function CatalogQuickAdd({
  name,
  onCreated,
  onClose,
}: {
  name: string;
  onCreated: (item: AddedItem) => void;
  onClose: () => void;
}) {
  const rights = useCatalogRights();
  const categories = useStreamedList<ExpenseCategory>(
    EXPENSE_CATEGORIES_PATH,
    100,
  );
  const mains = useStreamedList<ExpenseMainCategory>(
    EXPENSE_MAIN_CATEGORIES_PATH,
    100,
  );
  const inUse = categories.items
    .filter((category) => category.active !== false)
    .sort(byName);
  const editor = useCatalogEditor({
    mains: mains.items,
    categories: inUse,
    start: { kind: "item", name },
    onSaved: (saved) => {
      categories.reload();
      mains.reload();
      if (saved.kind === "item" && saved.created)
        onCreated({
          id: saved.id,
          name: saved.name,
          categoryName:
            inUse.find((category) => category.id === saved.link)?.name ?? "",
        });
    },
  });
  if (!editor.form) return null;
  return (
    <CatalogDialog
      key={editor.form.kind}
      form={editor.form}
      onChange={editor.change}
      mains={mains.items}
      categories={inUse}
      loadError={streamError(categories) || streamError(mains)}
      busy={editor.busy}
      onSave={() => void editor.submit()}
      onClose={editor.depth > 1 ? editor.close : onClose}
      onAddLink={rights.add ? editor.addLink : undefined}
    />
  );
}
