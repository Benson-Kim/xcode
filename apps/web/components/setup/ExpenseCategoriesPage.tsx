"use client";

import { useState } from "react";

import { streamError, useStreamedList } from "../../lib/data";
import {
  catalogApi,
  EXPENSE_CATEGORIES_PATH,
  EXPENSE_MAIN_CATEGORIES_PATH,
} from "../../lib/endpoints/catalog";
import { useFormats } from "../../lib/formats";
import { useSession } from "../../lib/session-context";
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
import {
  CatalogDialog,
  type CatalogForm,
  type CatalogKind,
} from "./CatalogDialog";

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
  const { can } = useSession();
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
  const [form, setForm] = useState<CatalogForm | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // The released expenses.setup key stands for adding, editing and stopping together.
  const manage = canManage || can("expenses.setup");
  const canAdd = manage || can("catalog.add");
  const canEdit = manage || can("catalog.edit");
  const canStop = manage || can("catalog.stop");

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

  function open(kind: CatalogKind, id: string | null = null) {
    const category = sortedCategories.find((candidate) => candidate.id === id);
    const item = rows.find((row) => row.item.id === id)?.item;
    const main = mains.items.find((candidate) => candidate.id === id);
    setForm({
      kind,
      id,
      name:
        (kind === "main" ? main : kind === "cat" ? category : item)?.name ?? "",
      link:
        kind === "cat"
          ? (category?.mainCategoryId ?? "")
          : kind === "item"
            ? (item?.categoryId ?? sortedCategories[0]?.id ?? "")
            : "",
      error: "",
    });
  }

  function problem(current: CatalogForm, name: string) {
    const lower = name.toLowerCase();
    const taken = (names: { id: string; name: string }[]) =>
      names.some(
        (other) =>
          other.id !== current.id && other.name.toLowerCase() === lower,
      );
    const clash = `${name} is already here.`;
    if (current.kind === "main")
      return !name
        ? "Enter the main category name."
        : taken(mains.items)
          ? clash
          : "";
    if (current.kind === "cat")
      return !name
        ? "Enter the category name."
        : taken(categories.items)
          ? clash
          : "";
    if (!name) return "Enter the item name.";
    if (!current.link) return "Choose the category.";
    return taken(
      categories.items.find((category) => category.id === current.link)
        ?.items ?? [],
    )
      ? clash
      : "";
  }

  async function submit(current: CatalogForm) {
    const name = current.name.trim();
    const refused = problem(current, name);
    if (refused) return setForm({ ...current, error: refused });
    const original =
      current.kind === "main"
        ? mains.items.find((main) => main.id === current.id)
        : current.kind === "cat"
          ? categories.items.find((category) => category.id === current.id)
          : rows.find((row) => row.item.id === current.id)?.item;
    const unchanged =
      original !== undefined &&
      name === original.name &&
      (current.kind === "cat"
        ? current.link === ((original as ExpenseCategory).mainCategoryId ?? "")
        : current.kind === "item"
          ? current.link === (original as ExpenseItem).categoryId
          : true);
    if (unchanged) return setForm(null);
    setBusy(true);
    try {
      if (current.kind === "main")
        await (current.id
          ? catalogApi.renameMain(current.id, name)
          : catalogApi.createMain(name));
      else if (current.kind === "cat") {
        const body = { name, mainCategoryId: current.link || null };
        await (current.id
          ? catalogApi.updateCategory(current.id, body)
          : catalogApi.createCategory(body));
      } else if (current.id) {
        const moved = current.link !== (original as ExpenseItem).categoryId;
        await catalogApi.updateItem(current.id, {
          name,
          ...(moved ? { categoryId: current.link } : {}),
        });
      } else await catalogApi.createItem(current.link, name);
      toast(
        current.id
          ? "Saved"
          : current.kind === "main"
            ? "Main category added"
            : current.kind === "cat"
              ? "Category added"
              : "Item added",
      );
      categories.reload();
      mains.reload();
      setForm(null);
    } catch (value) {
      setForm({ ...current, error: (value as Error).message });
    } finally {
      setBusy(false);
    }
  }

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
      {form && (
        <CatalogDialog
          form={form}
          setForm={setForm}
          mains={mains.items}
          categories={sortedCategories}
          busy={busy}
          onSave={() => void submit(form)}
          onClose={() => setForm(null)}
        />
      )}
    </>
  );
}
