"use client";

import { useState } from "react";

import { streamError, useStreamedList } from "../../lib/data";
import {
  catalogApi,
  EXPENSE_CATEGORIES_PATH,
  EXPENSE_MAIN_CATEGORIES_PATH,
} from "../../lib/endpoints/catalog";
import { useFormats } from "../../lib/formats";
import type {
  ExpenseCategory,
  ExpenseItem,
  ExpenseMainCategory,
} from "../../lib/types";
import {
  Banner,
  Button,
  DataTable,
  PageHeader,
  RowAction,
  Tabs,
  Td,
  Tr,
  useToast,
} from "../ui";
import { CatalogDialog, type CatalogKind } from "./CatalogDialog";
import { useCatalogEditor, useCatalogRights } from "./useCatalogEditor";

type Tab = "mains" | "cats" | "items";

const NEW_LABELS: Record<Tab, string> = {
  mains: "New main category",
  cats: "New category",
  items: "New item",
};
const TAB_KIND: Record<Tab, CatalogKind> = {
  mains: "main",
  cats: "cat",
  items: "item",
};

const byName = (left: { name: string }, right: { name: string }) =>
  left.name.localeCompare(right.name);

// Expense items in three levels: main categories group categories, and categories group the items people pick when
// they record an expense or a scheduled cost. Each level is changed with the catalog rights; catalog.view (or
// expenses.view, scheduled.view) only reads them.
export function ExpenseCategoriesPage({
  canManage = false,
}: {
  canManage?: boolean;
}) {
  const toast = useToast();
  const { formatDateOnly } = useFormats();
  const categories = useStreamedList<ExpenseCategory>(
    EXPENSE_CATEGORIES_PATH,
    100,
  );
  const mains = useStreamedList<ExpenseMainCategory>(
    EXPENSE_MAIN_CATEGORIES_PATH,
    100,
  );
  const [tab, setTab] = useState<Tab>("items");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The released expenses.setup key stands for adding, editing and stopping together.
  const rights = useCatalogRights(canManage);
  const canAdd = rights.add;
  const canEdit = rights.edit;
  const canStop = rights.stop;

  const sortedCategories = [...categories.items].sort(byName);
  const rows = sortedCategories.flatMap((category) =>
    [...category.items].sort(byName).map((item) => ({ item, category })),
  );
  const unset = categories.items.filter(
    (category) => !category.mainCategoryId,
  ).length;
  const inUse = rows.filter(({ item }) => item.active).length;
  const mainName = (category: ExpenseCategory) =>
    category.mainCategoryName ??
    mains.items.find((main) => main.id === category.mainCategoryId)?.name ??
    null;
  const editor = useCatalogEditor({
    mains: mains.items,
    categories: sortedCategories,
    onSaved: () => {
      categories.reload();
      mains.reload();
    },
  });
  const open = editor.open;

  async function toggle(item: ExpenseItem) {
    // The stored stop date decides, not active: that follows the business date, so a stop dated ahead of it still needs resuming to cancel.
    const stopped = Boolean(item.stoppedOn);
    setBusy(true);
    setError("");
    try {
      await catalogApi.setItemStopped(item.id, !stopped);
      toast(`${item.name} ${stopped ? "resumed" : "stopped"}.`);
      categories.reload();
      mains.reload();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const edit = (kind: CatalogKind, id: string, name: string) =>
    canEdit && (
      <RowAction
        disabled={busy}
        aria-label={`Edit ${name}`}
        onClick={() => open(kind, id)}
      >
        Edit
      </RowAction>
    );
  const actionColumn = (shown: boolean) =>
    shown ? [{ label: "Actions", numeric: true }] : [];
  const loadError = streamError(categories) || streamError(mains) || error;

  return (
    <>
      <PageHeader
        title="Expense items"
        actions={
          canAdd ? (
            <Button tone="primary" onClick={() => open(TAB_KIND[tab])}>
              {NEW_LABELS[tab]}
            </Button>
          ) : undefined
        }
      />
      {loadError && <Banner>{loadError}</Banner>}
      <Tabs
        id="expenses"
        label="Expense items"
        className="three"
        options={[
          {
            value: "mains" as const,
            label: "Main categories",
            note: mains.items.length,
          },
          {
            value: "cats" as const,
            label: "Categories",
            note: `${categories.items.length}${unset ? `, ${unset} with no main category` : ""}`,
          },
          { value: "items" as const, label: "Items", note: `${inUse} in use` },
        ]}
        value={tab}
        onChange={setTab}
      >
        {tab === "items" ? (
          <DataTable
            columns={[
              { label: "Item" },
              { label: "Category" },
              { label: "Main category" },
              { label: "Status" },
              ...actionColumn(canEdit || canStop),
            ]}
            loading={categories.loading}
            pendingRows={categories.pendingRows}
            loadingLabel="Loading expense items"
            isEmpty={!rows.length}
            failed={Boolean(categories.error)}
            emptyMessage="No items here yet."
          >
            {rows.map(({ item, category }) => {
              const main = mainName(category);
              return (
                <Tr key={item.id}>
                  <Td label="Item" item>
                    {item.name}
                  </Td>
                  <Td label="Category">{category.name}</Td>
                  <Td label="Main category">
                    {main ?? <span className="chip mute">Not set</span>}
                  </Td>
                  <Td label="Status">
                    {!item.active ? (
                      <span className="chip wait">Stopped</span>
                    ) : item.stoppedOn ? (
                      <span className="chip wait">
                        Stops {formatDateOnly(item.stoppedOn)}
                      </span>
                    ) : (
                      <span className="chip ok">In use</span>
                    )}
                  </Td>
                  {(canEdit || canStop) && (
                    <Td numeric>
                      <div className="tacts">
                        {edit("item", item.id, item.name)}
                        {canStop && (
                          <RowAction
                            tone={item.stoppedOn ? "ok" : "warn"}
                            disabled={busy}
                            aria-label={`${item.stoppedOn ? "Resume" : "Stop"} ${item.name}`}
                            onClick={() => void toggle(item)}
                          >
                            {item.stoppedOn ? "Resume" : "Stop"}
                          </RowAction>
                        )}
                      </div>
                    </Td>
                  )}
                </Tr>
              );
            })}
          </DataTable>
        ) : tab === "cats" ? (
          <DataTable
            columns={[
              { label: "Category" },
              { label: "Main category" },
              { label: "Items", numeric: true },
              ...actionColumn(canEdit),
            ]}
            loading={categories.loading}
            pendingRows={categories.pendingRows}
            loadingLabel="Loading expense categories"
            isEmpty={!sortedCategories.length}
            failed={Boolean(categories.error)}
            emptyMessage="No categories yet."
          >
            {sortedCategories.map((category) => {
              const main = mainName(category);
              return (
                <Tr key={category.id}>
                  <Td label="Category" item>
                    {category.name}
                  </Td>
                  <Td label="Main category">
                    {main ?? <span className="chip mute">Not set</span>}
                  </Td>
                  <Td label="Items" numeric>
                    {category.items.length}
                  </Td>
                  {canEdit && (
                    <Td numeric>
                      <div className="tacts">
                        {edit("cat", category.id, category.name)}
                      </div>
                    </Td>
                  )}
                </Tr>
              );
            })}
          </DataTable>
        ) : (
          <DataTable
            columns={[
              { label: "Main category" },
              { label: "Categories", numeric: true },
              { label: "Items", numeric: true },
              ...actionColumn(canEdit),
            ]}
            loading={mains.loading}
            pendingRows={mains.pendingRows}
            loadingLabel="Loading main categories"
            isEmpty={!mains.items.length}
            failed={Boolean(mains.error)}
            emptyMessage="No main categories yet."
          >
            {mains.items.map((main) => (
              <Tr key={main.id}>
                <Td label="Main category" item>
                  {main.name}
                </Td>
                <Td label="Categories" numeric>
                  {main.categoryCount}
                </Td>
                <Td label="Items" numeric>
                  {main.itemCount}
                </Td>
                {canEdit && (
                  <Td numeric>
                    <div className="tacts">
                      {edit("main", main.id, main.name)}
                    </div>
                  </Td>
                )}
              </Tr>
            ))}
          </DataTable>
        )}
      </Tabs>
      {editor.form && (
        <CatalogDialog
          key={editor.form.kind}
          form={editor.form}
          onChange={editor.change}
          mains={mains.items}
          categories={sortedCategories}
          busy={editor.busy}
          onSave={() => void editor.submit()}
          onClose={editor.close}
          onAddLink={canAdd ? editor.addLink : undefined}
        />
      )}
    </>
  );
}
