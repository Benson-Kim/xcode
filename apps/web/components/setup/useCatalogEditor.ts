"use client";

import { useState } from "react";

import { catalogApi } from "../../lib/endpoints/catalog";
import { useSession } from "../../lib/session-context";
import type {
  ExpenseCategory,
  ExpenseItem,
  ExpenseMainCategory,
} from "../../lib/types";
import { useToast } from "../ui";
import type { CatalogForm, CatalogKind } from "./CatalogDialog";

export type CatalogSaved = {
  kind: CatalogKind;
  id: string;
  created: boolean;
  name: string;
  link: string;
};

const ADDED: Record<CatalogKind, string> = {
  main: "Main category added",
  cat: "Category added",
  item: "Item added",
};

// The level a form's link chooses from: a category's main category, an item's category.
const LINK_KIND: Partial<Record<CatalogKind, CatalogKind>> = {
  cat: "main",
  item: "cat",
};

export function useCatalogRights(canManage = false) {
  const { can } = useSession();
  const manage = canManage || can("expenses.setup");
  return {
    add: manage || can("catalog.add"),
    edit: manage || can("catalog.edit"),
    stop: manage || can("catalog.stop"),
  };
}

function problem(
  current: CatalogForm,
  name: string,
  mains: ExpenseMainCategory[],
  categories: ExpenseCategory[],
) {
  const lower = name.toLowerCase();
  const taken = (names: { id: string; name: string }[]) =>
    names.some(
      (other) => other.id !== current.id && other.name.toLowerCase() === lower,
    );
  const clash = `${name} is already here.`;
  if (current.kind === "main")
    return !name ? "Enter the main category name." : taken(mains) ? clash : "";
  if (current.kind === "cat")
    return !name ? "Enter the category name." : taken(categories) ? clash : "";
  if (!name) return "Enter the item name.";
  if (!current.link) return "Choose the category.";
  return taken(
    categories.find((category) => category.id === current.link)?.items ?? [],
  )
    ? clash
    : "";
}

// The catalog's add and edit pop ups. A form's "+ Add new" opens the level above it on top; saving that one puts
// the new entry in the form below, and cancelling it goes back to that form as it was.
export function useCatalogEditor({
  mains,
  categories,
  onSaved,
  start,
}: {
  mains: ExpenseMainCategory[];
  categories: ExpenseCategory[];
  onSaved: (saved: CatalogSaved) => void;
  // Opens straight on a new entry with this name, as "+ Add new" in another form does.
  start?: { kind: CatalogKind; name: string };
}) {
  const toast = useToast();
  const [stack, setStack] = useState<CatalogForm[]>(() =>
    start ? [{ ...start, id: null, link: "", error: "" }] : [],
  );
  const [busy, setBusy] = useState(false);
  const form = stack.at(-1) ?? null;
  const items = categories.flatMap((category) => category.items);

  const replaceTop = (next: CatalogForm) =>
    setStack((current) => [...current.slice(0, -1), next]);

  function open(kind: CatalogKind, id: string | null = null, name = "") {
    const category = categories.find((candidate) => candidate.id === id);
    const item = items.find((candidate) => candidate.id === id);
    const main = mains.find((candidate) => candidate.id === id);
    setStack([
      {
        kind,
        id,
        name:
          (kind === "main" ? main : kind === "cat" ? category : item)?.name ??
          name,
        link:
          kind === "cat"
            ? (category?.mainCategoryId ?? "")
            : kind === "item"
              ? (item?.categoryId ?? categories[0]?.id ?? "")
              : "",
        error: "",
      },
    ]);
  }

  function addLink(typed: string) {
    const kind = form && LINK_KIND[form.kind];
    if (!kind) return;
    setStack((current) => [
      ...current,
      { kind, id: null, name: typed, link: "", error: "" },
    ]);
  }

  const close = () => setStack((current) => current.slice(0, -1));

  function unchanged(current: CatalogForm, name: string) {
    const original =
      current.kind === "main"
        ? mains.find((main) => main.id === current.id)
        : current.kind === "cat"
          ? categories.find((category) => category.id === current.id)
          : items.find((item) => item.id === current.id);
    if (original === undefined || name !== original.name) return false;
    if (current.kind === "cat")
      return (
        current.link === ((original as ExpenseCategory).mainCategoryId ?? "")
      );
    if (current.kind === "item")
      return current.link === (original as ExpenseItem).categoryId;
    return true;
  }

  async function write(current: CatalogForm, name: string) {
    if (current.kind === "main")
      return current.id
        ? catalogApi.renameMain(current.id, name)
        : catalogApi.createMain(name);
    if (current.kind === "cat") {
      const body = { name, mainCategoryId: current.link || null };
      return current.id
        ? catalogApi.updateCategory(current.id, body)
        : catalogApi.createCategory(body);
    }
    if (!current.id) return catalogApi.createItem(current.link, name);
    const moved =
      current.link !== items.find((item) => item.id === current.id)?.categoryId;
    return catalogApi.updateItem(current.id, {
      name,
      ...(moved ? { categoryId: current.link } : {}),
    });
  }

  async function submit() {
    if (!form) return;
    const current = form;
    const name = current.name.trim();
    const refused = problem(current, name, mains, categories);
    if (refused) return replaceTop({ ...current, error: refused });
    if (unchanged(current, name)) return close();
    setBusy(true);
    try {
      const { id } = await write(current, name);
      toast(current.id ? "Saved" : ADDED[current.kind]);
      setStack((open) => {
        const below = open.slice(0, -2);
        const parent = open.at(-2);
        return parent ? [...below, { ...parent, link: id, error: "" }] : [];
      });
      onSaved({
        kind: current.kind,
        id,
        created: !current.id,
        name,
        link: current.link,
      });
    } catch (value) {
      replaceTop({ ...current, error: (value as Error).message });
    } finally {
      setBusy(false);
    }
  }

  return {
    form,
    depth: stack.length,
    busy,
    open,
    addLink,
    close,
    submit,
    change: replaceTop,
  };
}
