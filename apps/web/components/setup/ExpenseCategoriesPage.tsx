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
import { useDeleteRecord } from "./DeleteRecordDialog";
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
const NOUNS: Record<CatalogKind, string> = {
  main: "main category",
  cat: "category",
  item: "item",
};
const DELETE: Record<CatalogKind, (id: string) => Promise<unknown>> = {
  main: catalogApi.deleteMain,
  cat: catalogApi.deleteCategory,
  item: catalogApi.deleteItem,
};

type Named = { id: string; name: string };
type Stoppable = Named & { active: boolean; stoppedOn: string | null };
type ListState = {
  loading: boolean;
  pendingRows: number;
  error?: unknown;
};

// What each row may offer, by the catalog rights: edit, stop or resume, and delete, which goes with stopping.
type RowActions = {
  canEdit: boolean;
  canStop: boolean;
  busy: boolean;
  onEdit: (kind: CatalogKind, id: string) => void;
  onStop: (kind: "cat" | "item", record: Stoppable) => void;
  onDelete: (kind: CatalogKind, record: Named) => void;
};

const byName = (left: { name: string }, right: { name: string }) =>
  left.name.localeCompare(right.name);

const tableState = (list: ListState) => ({
  loading: list.loading,
  pendingRows: list.pendingRows,
  failed: Boolean(list.error),
});

const actionColumn = (actions: RowActions) =>
  actions.canEdit || actions.canStop
    ? [{ label: "Actions", numeric: true }]
    : [];

// Expense items in three levels: main categories group categories, and categories group the items people pick when
// they record an expense or a scheduled cost. Each level is changed with the catalog rights; catalog.view (or
// expenses.view, scheduled.view) only reads them. A record added by mistake can be deleted while nothing uses it:
// a main category with no categories, a category with no items, and any item, which the server checks.
export function ExpenseCategoriesPage({
  canManage = false,
}: {
  canManage?: boolean;
}) {
  const toast = useToast();
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
  const reload = () => {
    categories.reload();
    mains.reload();
  };
  const editor = useCatalogEditor({
    mains: mains.items,
    categories: sortedCategories,
    onSaved: reload,
  });
  const deletion = useDeleteRecord(reload);

  // The stored stop date decides, not active: that follows the business date, so a stop dated ahead of it still needs resuming to cancel.
  async function toggle(kind: "cat" | "item", record: Stoppable) {
    const stopped = Boolean(record.stoppedOn);
    setBusy(true);
    setError("");
    try {
      await (
        kind === "item"
          ? catalogApi.setItemStopped
          : catalogApi.setCategoryStopped
      )(record.id, !stopped);
      toast(`${record.name} ${stopped ? "resumed" : "stopped"}.`);
      reload();
    } catch (value) {
      setError((value as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const actions: RowActions = {
    canEdit: rights.edit,
    canStop: rights.stop,
    busy,
    onEdit: editor.open,
    onStop: (kind, record) => void toggle(kind, record),
    onDelete: (kind, record) =>
      deletion.ask({
        noun: NOUNS[kind],
        name: record.name,
        remove: () => DELETE[kind](record.id),
      }),
  };
  const loadError = streamError(categories) || streamError(mains) || error;

  return (
    <>
      <PageHeader
        title="Expense items"
        actions={
          rights.add ? (
            <Button tone="primary" onClick={() => editor.open(TAB_KIND[tab])}>
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
          <ItemsTable
            rows={rows}
            mainName={mainName}
            list={categories}
            actions={actions}
          />
        ) : tab === "cats" ? (
          <CategoriesTable
            categories={sortedCategories}
            mainName={mainName}
            list={categories}
            actions={actions}
          />
        ) : (
          <MainsTable mains={mains.items} list={mains} actions={actions} />
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
          onAddLink={rights.add ? editor.addLink : undefined}
        />
      )}
      {deletion.dialog}
    </>
  );
}

function ItemsTable({
  rows,
  mainName,
  list,
  actions,
}: {
  rows: { item: ExpenseItem; category: ExpenseCategory }[];
  mainName: (category: ExpenseCategory) => string | null;
  list: ListState;
  actions: RowActions;
}) {
  return (
    <DataTable
      columns={[
        { label: "Item" },
        { label: "Category" },
        { label: "Main category" },
        { label: "Status" },
        ...actionColumn(actions),
      ]}
      {...tableState(list)}
      loadingLabel="Loading expense items"
      isEmpty={!rows.length}
      emptyMessage="No items here yet."
    >
      {rows.map(({ item, category }) => (
        <Tr key={item.id}>
          <Td label="Item" item>
            {item.name}
          </Td>
          <Td label="Category">{category.name}</Td>
          <Td label="Main category">
            <MainName name={mainName(category)} />
          </Td>
          <Td label="Status">
            <StopStatus record={item} />
          </Td>
          <CatalogRowActions
            kind="item"
            record={item}
            actions={actions}
            deletable
          />
        </Tr>
      ))}
    </DataTable>
  );
}

function CategoriesTable({
  categories,
  mainName,
  list,
  actions,
}: {
  categories: ExpenseCategory[];
  mainName: (category: ExpenseCategory) => string | null;
  list: ListState;
  actions: RowActions;
}) {
  return (
    <DataTable
      columns={[
        { label: "Category" },
        { label: "Main category" },
        { label: "Items", numeric: true },
        { label: "Status" },
        ...actionColumn(actions),
      ]}
      {...tableState(list)}
      loadingLabel="Loading expense categories"
      isEmpty={!categories.length}
      emptyMessage="No categories yet."
    >
      {categories.map((category) => (
        <Tr key={category.id}>
          <Td label="Category" item>
            {category.name}
          </Td>
          <Td label="Main category">
            <MainName name={mainName(category)} />
          </Td>
          <Td label="Items" numeric>
            {category.items.length}
          </Td>
          <Td label="Status">
            <StopStatus record={category} />
          </Td>
          <CatalogRowActions
            kind="cat"
            record={category}
            actions={actions}
            deletable={category.items.length === 0}
          />
        </Tr>
      ))}
    </DataTable>
  );
}

function MainsTable({
  mains,
  list,
  actions,
}: {
  mains: ExpenseMainCategory[];
  list: ListState;
  actions: RowActions;
}) {
  return (
    <DataTable
      columns={[
        { label: "Main category" },
        { label: "Categories", numeric: true },
        { label: "Items", numeric: true },
        ...actionColumn(actions),
      ]}
      {...tableState(list)}
      loadingLabel="Loading main categories"
      isEmpty={!mains.length}
      emptyMessage="No main categories yet."
    >
      {mains.map((main) => (
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
          <CatalogRowActions
            kind="main"
            record={main}
            actions={actions}
            deletable={main.categoryCount === 0}
          />
        </Tr>
      ))}
    </DataTable>
  );
}

function MainName({ name }: { name: string | null }) {
  return name ?? <span className="chip mute">Not set</span>;
}

function StopStatus({ record }: { record: Stoppable }) {
  const { formatDateOnly } = useFormats();
  if (!record.active) return <span className="chip wait">Stopped</span>;
  if (record.stoppedOn)
    return (
      <span className="chip wait">
        Stops {formatDateOnly(record.stoppedOn)}
      </span>
    );
  return <span className="chip ok">In use</span>;
}

function CatalogRowActions({
  kind,
  record,
  actions,
  deletable,
}: {
  kind: CatalogKind;
  record: Named | Stoppable;
  actions: RowActions;
  deletable: boolean;
}) {
  const { canEdit, canStop, busy } = actions;
  if (!canEdit && !canStop) return null;
  const stoppable = "stoppedOn" in record ? record : null;
  return (
    <Td numeric>
      <div className="tacts">
        {canEdit && (
          <RowAction
            disabled={busy}
            aria-label={`Edit ${record.name}`}
            onClick={() => actions.onEdit(kind, record.id)}
          >
            Edit
          </RowAction>
        )}
        {canStop && stoppable && kind !== "main" && (
          <RowAction
            tone={stoppable.stoppedOn ? "ok" : "warn"}
            disabled={busy}
            aria-label={`${stoppable.stoppedOn ? "Resume" : "Stop"} ${record.name}`}
            onClick={() => actions.onStop(kind, stoppable)}
          >
            {stoppable.stoppedOn ? "Resume" : "Stop"}
          </RowAction>
        )}
        {canStop && deletable && (
          <RowAction
            tone="bad"
            disabled={busy}
            aria-label={`Delete ${record.name}`}
            onClick={() => actions.onDelete(kind, record)}
          >
            Delete
          </RowAction>
        )}
      </div>
    </Td>
  );
}
