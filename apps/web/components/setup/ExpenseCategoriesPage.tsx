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
  ErrorText,
  Field,
  FormActions,
  Hint,
  PageHeader,
  SelectInput,
  Spacer,
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
    if (editing?.id === entity.id)
      return (
        <FormActions className="justify-end">
          <Button
            tone="ok"
            disabled={busy}
            onClick={() => void saveEdit(entity)}
          >
            Save
          </Button>
          <Button tone="quiet" onClick={() => setEditing(null)}>
            Cancel
          </Button>
        </FormActions>
      );
    return (
      <FormActions className="justify-end">
        <Button
          tone="outline"
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
        </Button>
        <Button
          tone={entity.stoppedOn ? "ok" : "warn"}
          disabled={busy}
          aria-label={`${entity.stoppedOn ? "Turn on" : "Turn off"} ${entity.name}`}
          onClick={() => void toggle(kind, entity)}
        >
          {entity.stoppedOn ? "Turn on" : "Turn off"}
        </Button>
      </FormActions>
    );
  }

  function nameEditor(label: string, original: ExpenseCategory | ExpenseItem) {
    if (!editing) return null;
    return (
      <>
        <TextInput
          autoFocus
          density="compact"
          aria-label={label}
          maxLength={NAME_LIMIT}
          value={editing.name}
          aria-invalid={Boolean(editing.error) || undefined}
          aria-describedby={editing.error ? "expense-edit-error" : undefined}
          onChange={(event) =>
            setEditing({ ...editing, name: event.target.value, error: "" })
          }
          onKeyDown={(event) => {
            if (event.key === "Enter") void saveEdit(original);
            if (event.key === "Escape") setEditing(null);
          }}
        />
        {editing.error && (
          <ErrorText id="expense-edit-error">{editing.error}</ErrorText>
        )}
      </>
    );
  }

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
      />
      {(categories.error || error) && (
        <Banner className="mt-5">{streamError(categories) || error}</Banner>
      )}
      {!canManage && (
        <p className="mt-3 mb-0 text-[13px] text-grey">
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
              <Spacer />
              {canManage && (
                <Button tone="ok" onClick={() => openAdd("item")}>
                  Add item
                </Button>
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
                    {editing?.id === item.id ? (
                      nameEditor("Item name", item)
                    ) : (
                      <strong
                        className={cn(!item.active && "text-grey line-through")}
                      >
                        {item.name}
                      </strong>
                    )}
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
              <Spacer />
              {canManage && (
                <Button tone="ok" onClick={() => openAdd("category")}>
                  Add category
                </Button>
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
                    {editing?.id === category.id ? (
                      nameEditor("Category name", category)
                    ) : (
                      <strong
                        className={cn(
                          !category.active && "text-grey line-through",
                        )}
                      >
                        {category.name}
                      </strong>
                    )}
                  </Td>
                  <Td label="Counts as">
                    {editing?.id === category.id ? (
                      <SelectInput
                        density="compact"
                        aria-label="Counts as"
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
                    ) : (
                      expenseBucketNames[category.bucket]
                    )}
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
      >
        {adding && (
          <div className="flex flex-col gap-3.5">
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
                onKeyDown={(event) => {
                  if (event.key === "Enter") void add();
                }}
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
            <FormActions>
              <Button tone="ok" disabled={busy} onClick={() => void add()}>
                Add
              </Button>
              <Button tone="quiet" onClick={() => setAdding(null)}>
                Cancel
              </Button>
            </FormActions>
          </div>
        )}
      </Dialog>
    </section>
  );
}
