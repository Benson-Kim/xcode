"use client";

import { useState } from "react";

import { plural } from "@xcode/shared/format";

import { apiRequest, streamError, useStreamedList } from "../../lib/data";
import { useFormats } from "../../lib/formats";
import type {
  ExpenseBucket,
  ExpenseCategory,
  ExpenseItem,
} from "../../lib/types";
import {
  Banner,
  Button,
  CellNote,
  DataTable,
  Dialog,
  Field,
  Hint,
  PageHeader,
  RowAction,
  SelectInput,
  StatusBadge,
  Tabs,
  Td,
  TextInput,
  Toolbar,
  Tr,
  cn,
  useToast,
} from "../ui";
import { expenseBucketNames } from "./shared";

type Kind = "category" | "item";
type Status = "all" | "on" | "off";
// A new category or item in the pop-up, or the row being changed in place.
type Adding = {
  kind: Kind;
  name: string;
  bucket: ExpenseBucket;
  categoryId: string;
  error: string;
};
type Editing = {
  kind: Kind;
  id: string;
  name: string;
  bucket: ExpenseBucket;
  error: string;
};

const buckets: ExpenseBucket[] = [1, 2, 3];
const NAME_LIMIT = 100;

// Expense categories, each counting in one of the three buckets, and the items people pick when they record an
// expense or a scheduled cost. Changing them needs expenses.setup; expenses.view or commitments.view only reads them.
export function ExpenseCategoriesPage({ canManage }: { canManage: boolean }) {
  const categories = useStreamedList<ExpenseCategory>(
    "setup/expense-categories",
    100,
  );
  const toast = useToast();
  const { formatDateOnly } = useFormats();
  const [tab, setTab] = useState<"items" | "categories">("items");
  const [status, setStatus] = useState<Status>("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [adding, setAdding] = useState<Adding | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const shown = (active: boolean) =>
    status === "all" || (status === "off") === !active;
  // Grouped by the bucket each category counts in, then by name.
  const sorted = [...categories.items].sort(
    (left, right) =>
      left.bucket - right.bucket || left.name.localeCompare(right.name),
  );
  const visibleCategories = sorted.filter((category) => shown(category.active));
  const visibleItems = sorted
    .filter(
      (category) => categoryFilter === "all" || category.id === categoryFilter,
    )
    .flatMap((category) =>
      [...category.items]
        .sort((left, right) => left.name.localeCompare(right.name))
        .map((item) => ({ item, category })),
    )
    .filter(({ item }) => shown(item.active));

  function clash(
    kind: Kind,
    name: string,
    categoryId: string,
    except?: string,
  ) {
    const lower = name.toLowerCase();
    if (kind === "category")
      return sorted.some(
        (category) =>
          category.id !== except && category.name.toLowerCase() === lower,
      );
    return (
      sorted.find((category) => category.id === categoryId)?.items ?? []
    ).some((item) => item.id !== except && item.name.toLowerCase() === lower);
  }

  function nameProblem(
    kind: Kind,
    name: string,
    categoryId: string,
    except?: string,
  ) {
    if (!name) return "Enter the name.";
    if (kind === "item" && !categoryId) return "Add a category first.";
    if (clash(kind, name, categoryId, except))
      return kind === "category"
        ? "That category already exists."
        : "That item already exists in this category.";
    return "";
  }

  async function send(path: string, method: string, body: object) {
    setBusy(true);
    try {
      await apiRequest(path, { method, body: JSON.stringify(body) });
      categories.reload();
      return "";
    } catch (value) {
      return (value as Error).message;
    } finally {
      setBusy(false);
    }
  }

  function openAdd(kind: Kind) {
    setError("");
    setAdding({
      kind,
      name: "",
      bucket: 1,
      categoryId:
        categoryFilter !== "all"
          ? categoryFilter
          : (sorted.find((category) => category.active)?.id ?? ""),
      error: "",
    });
  }

  async function add() {
    if (!adding) return;
    const name = adding.name.trim();
    const problem = nameProblem(adding.kind, name, adding.categoryId);
    if (problem) return setAdding({ ...adding, error: problem });
    const failed =
      adding.kind === "category"
        ? await send("setup/expense-categories", "POST", {
            name,
            bucket: adding.bucket,
          })
        : await send(
            `setup/expense-categories/${adding.categoryId}/items`,
            "POST",
            { name },
          );
    if (failed) return setAdding({ ...adding, error: failed });
    toast(`${name} added.`);
    setTab(adding.kind === "category" ? "categories" : "items");
    setAdding(null);
  }

  async function saveEdit(original: ExpenseCategory | ExpenseItem) {
    if (!editing) return;
    const name = editing.name.trim();
    const categoryId =
      "categoryId" in original ? original.categoryId : original.id;
    const problem = nameProblem(editing.kind, name, categoryId, original.id);
    if (problem) return setEditing({ ...editing, error: problem });
    const unchanged =
      name === original.name &&
      ("bucket" in original ? original.bucket === editing.bucket : true);
    if (unchanged) return setEditing(null);
    const failed =
      editing.kind === "category"
        ? await send(`setup/expense-categories/${original.id}`, "PUT", {
            name,
            bucket: editing.bucket,
          })
        : await send(`setup/expense-items/${original.id}`, "PUT", { name });
    if (failed) return setEditing({ ...editing, error: failed });
    toast("Saved.");
    setEditing(null);
  }

  async function toggle(kind: Kind, entity: ExpenseCategory | ExpenseItem) {
    const base =
      kind === "category"
        ? `setup/expense-categories/${entity.id}`
        : `setup/expense-items/${entity.id}`;
    // The stored stop date decides, not `active`: that follows the business date, so a stop dated ahead of it still needs turning on to cancel.
    const off = Boolean(entity.stoppedOn);
    const failed = await send(
      `${base}/${off ? "restore" : "stop"}`,
      "POST",
      {},
    );
    setError(failed);
    if (failed) return;
    setEditing(null);
    toast(`${entity.name} ${off ? "turned on" : "turned off"}.`);
  }

  function actions(kind: Kind, entity: ExpenseCategory | ExpenseItem) {
    return (
      <div className="flex items-center justify-end gap-0.5 whitespace-nowrap">
        <RowAction
          disabled={busy}
          aria-label={`Edit ${entity.name}`}
          onClick={() => {
            setError("");
            setEditing({
              kind,
              id: entity.id,
              name: entity.name,
              bucket: "bucket" in entity ? entity.bucket : 1,
              error: "",
            });
          }}
        >
          Edit
        </RowAction>
        <RowAction
          tone={entity.stoppedOn ? "ok" : "warn"}
          disabled={busy}
          aria-label={`${entity.stoppedOn ? "Turn on" : "Turn off"} ${entity.name}`}
          onClick={() => void toggle(kind, entity)}
        >
          {entity.stoppedOn ? "Turn on" : "Turn off"}
        </RowAction>
      </div>
    );
  }

  const editingEntity = editing
    ? editing.kind === "category"
      ? sorted.find((category) => category.id === editing.id)
      : sorted
          .flatMap((category) => category.items)
          .find((item) => item.id === editing.id)
    : undefined;

  const statusFilter = (
    <>
      <label htmlFor="expense-status" className="text-[13px] text-grey">
        Show
      </label>
      <SelectInput
        id="expense-status"
        density="compact"
        inline
        value={status}
        onChange={(event) => setStatus(event.target.value as Status)}
      >
        <option value="all">All</option>
        <option value="on">In use</option>
        <option value="off">Turned off</option>
      </SelectInput>
    </>
  );
  const statusCell = (entity: ExpenseCategory | ExpenseItem) => (
    <Td label="Status">
      <StatusBadge tone={entity.active ? "ok" : "off"}>
        {!entity.active
          ? "Turned off"
          : entity.stoppedOn
            ? `Turns off on ${formatDateOnly(entity.stoppedOn)}`
            : "In use"}
      </StatusBadge>
    </Td>
  );
  const actionColumn = canManage ? [{ label: "Actions", hidden: true }] : [];

  return (
    <section>
      <PageHeader
        title="Expense categories"
        description="Items are what people pick when they record an expense, in petty cash and in other expenses."
        actions={
          canManage ? (
            <Button
              tone="primary"
              onClick={() => openAdd(tab === "items" ? "item" : "category")}
            >
              {tab === "items" ? "Add item" : "Add category"}
            </Button>
          ) : undefined
        }
      />
      {(categories.error || error) && (
        <Banner className="mb-3.5">{streamError(categories) || error}</Banner>
      )}
      {!canManage && (
        <p className="m-0 mb-3.5 text-[13px] text-grey">
          You can see the categories and items but not change them.
        </p>
      )}
      <Tabs
        id="expenses"
        label="Expense categories"
        options={[
          { value: "items", label: "Items" },
          { value: "categories", label: "Categories" },
        ]}
        value={tab}
        onChange={(next) => {
          setTab(next);
          setEditing(null);
        }}
      >
        {tab === "items" ? (
          <>
            <Toolbar>
              <label
                htmlFor="expense-category"
                className="text-[13px] text-grey"
              >
                Category
              </label>
              <SelectInput
                id="expense-category"
                density="compact"
                inline
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
              >
                <option value="all">All categories</option>
                {sorted.map((category) => (
                  <option key={category.id} value={category.id}>
                    {category.name}
                  </option>
                ))}
              </SelectInput>
              {statusFilter}
              {!categories.loading && (
                <Hint>{plural(visibleItems.length, "item", "items")}</Hint>
              )}
            </Toolbar>
            <DataTable
              columns={[
                { label: "Item" },
                { label: "Category" },
                { label: "Status" },
                ...actionColumn,
              ]}
              loading={categories.loading}
              pendingRows={categories.pendingRows}
              loadingLabel="Loading expense items"
              isEmpty={!visibleItems.length}
              failed={Boolean(categories.error)}
              emptyMessage="No items here yet."
            >
              {visibleItems.map(({ item, category }) => (
                <Tr key={item.id}>
                  <Td label="Item">
                    <span
                      className={cn(
                        "font-semibold text-ink",
                        !item.active && "text-grey line-through",
                      )}
                    >
                      {item.name}
                    </span>
                  </Td>
                  <Td label="Category">
                    {category.name}
                    <CellNote>
                      {category.active
                        ? `Counts as ${expenseBucketNames[category.bucket]}`
                        : "Its category is turned off"}
                    </CellNote>
                  </Td>
                  {statusCell(item)}
                  {canManage && <Td>{actions("item", item)}</Td>}
                </Tr>
              ))}
            </DataTable>
          </>
        ) : (
          <>
            <Toolbar>
              {statusFilter}
              {!categories.loading && (
                <Hint>
                  {plural(visibleCategories.length, "category", "categories")}
                </Hint>
              )}
            </Toolbar>
            <DataTable
              columns={[
                { label: "Category" },
                { label: "Counts as" },
                { label: "Items", numeric: true },
                { label: "Status" },
                ...actionColumn,
              ]}
              loading={categories.loading}
              pendingRows={categories.pendingRows}
              loadingLabel="Loading expense categories"
              isEmpty={!visibleCategories.length}
              failed={Boolean(categories.error)}
              emptyMessage="No categories here yet."
            >
              {visibleCategories.map((category) => (
                <Tr key={category.id}>
                  <Td label="Category">
                    <span
                      className={cn(
                        "font-semibold text-ink",
                        !category.active && "text-grey line-through",
                      )}
                    >
                      {category.name}
                    </span>
                  </Td>
                  <Td label="Counts as">
                    {expenseBucketNames[category.bucket]}
                  </Td>
                  <Td label="Items" numeric>
                    {category.items.filter((item) => item.active).length}
                  </Td>
                  {statusCell(category)}
                  {canManage && <Td>{actions("category", category)}</Td>}
                </Tr>
              ))}
            </DataTable>
          </>
        )}
      </Tabs>
      <Dialog
        open={Boolean(adding)}
        title={adding?.kind === "category" ? "New category" : "New item"}
        onClose={() => setAdding(null)}
        footer={
          <>
            <Button tone="outline" onClick={() => setAdding(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="expense-add-form"
              tone="ok"
              disabled={busy}
            >
              Add
            </Button>
          </>
        }
      >
        {adding && (
          <form
            id="expense-add-form"
            className="flex flex-col gap-3.5"
            onSubmit={(event) => {
              event.preventDefault();
              void add();
            }}
          >
            <Field id="expense-new-name" label="Name">
              <TextInput
                autoFocus
                maxLength={NAME_LIMIT}
                value={adding.name}
                placeholder={
                  adding.kind === "category"
                    ? "For example Bodywork"
                    : "For example Brake pads"
                }
                onChange={(event) =>
                  setAdding({ ...adding, name: event.target.value, error: "" })
                }
              />
            </Field>
            {adding.kind === "category" ? (
              <Field id="expense-new-bucket" label="Counts as">
                <SelectInput
                  value={adding.bucket}
                  onChange={(event) =>
                    setAdding({
                      ...adding,
                      bucket: Number(event.target.value) as ExpenseBucket,
                    })
                  }
                >
                  {buckets.map((bucket) => (
                    <option key={bucket} value={bucket}>
                      {expenseBucketNames[bucket]}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            ) : (
              <Field id="expense-new-category" label="Category">
                <SelectInput
                  value={adding.categoryId}
                  onChange={(event) =>
                    setAdding({
                      ...adding,
                      categoryId: event.target.value,
                      error: "",
                    })
                  }
                >
                  {sorted.map((category) => (
                    <option key={category.id} value={category.id}>
                      {category.name}
                      {category.active ? "" : " (turned off)"}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            )}
            {adding.error && <Banner>{adding.error}</Banner>}
          </form>
        )}
      </Dialog>
      <Dialog
        open={Boolean(editing && editingEntity)}
        title={editing?.kind === "category" ? "Edit category" : "Edit item"}
        subtitle={editingEntity?.name}
        onClose={() => setEditing(null)}
        footer={
          <>
            <Button tone="outline" onClick={() => setEditing(null)}>
              Cancel
            </Button>
            <Button
              type="submit"
              form="expense-edit-form"
              tone="ok"
              disabled={busy}
            >
              Save
            </Button>
          </>
        }
      >
        {editing && editingEntity && (
          <form
            id="expense-edit-form"
            className="flex flex-col gap-3.5"
            onSubmit={(event) => {
              event.preventDefault();
              void saveEdit(editingEntity);
            }}
          >
            <Field
              id="expense-edit-name"
              label={
                editing.kind === "category" ? "Category name" : "Item name"
              }
              error={editing.error}
            >
              <TextInput
                autoFocus
                maxLength={NAME_LIMIT}
                value={editing.name}
                onChange={(event) =>
                  setEditing({
                    ...editing,
                    name: event.target.value,
                    error: "",
                  })
                }
              />
            </Field>
            {editing.kind === "category" && (
              <Field id="expense-edit-bucket" label="Counts as">
                <SelectInput
                  value={editing.bucket}
                  onChange={(event) =>
                    setEditing({
                      ...editing,
                      bucket: Number(event.target.value) as ExpenseBucket,
                    })
                  }
                >
                  {buckets.map((bucket) => (
                    <option key={bucket} value={bucket}>
                      {expenseBucketNames[bucket]}
                    </option>
                  ))}
                </SelectInput>
              </Field>
            )}
          </form>
        )}
      </Dialog>
    </section>
  );
}
