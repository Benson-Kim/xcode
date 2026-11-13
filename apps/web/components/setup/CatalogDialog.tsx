"use client";

import type { ExpenseCategory, ExpenseMainCategory } from "../../lib/types";
import {
  Button,
  Dialog,
  ErrorText,
  Field,
  SearchSelect,
  TextInput,
} from "../ui";

export type CatalogKind = "main" | "cat" | "item";

// The pop up's fields: the name, and the main category (for a category) or the category (for an item) chosen.
export type CatalogForm = {
  kind: CatalogKind;
  id: string | null;
  name: string;
  link: string;
  error: string;
};

const KIND_NAMES: Record<CatalogKind, string> = {
  main: "main category",
  cat: "category",
  item: "item",
};

export function CatalogDialog({
  form,
  onChange,
  mains,
  categories,
  busy,
  onSave,
  onClose,
  onAddLink,
  loadError = "",
}: {
  form: CatalogForm;
  onChange: (form: CatalogForm) => void;
  mains: ExpenseMainCategory[];
  categories: ExpenseCategory[];
  busy: boolean;
  // Why the main categories or categories to choose from did not load.
  loadError?: string;
  onSave: () => void;
  onClose: () => void;
  // Given, the main category or category list starts with "+ Add new".
  onAddLink?: (typed: string) => void;
}) {
  const change = (next: Partial<CatalogForm>) =>
    onChange({ ...form, ...next, error: "" });
  return (
    <Dialog
      open
      size="sm"
      title={`${form.id ? "Edit" : "New"} ${KIND_NAMES[form.kind]}`}
      busy={busy}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" disabled={busy} onClick={onClose}>
            Cancel
          </Button>
          <Button type="submit" form="catalog-form" tone="ok" disabled={busy}>
            Save
          </Button>
        </>
      }
    >
      <form
        id="catalog-form"
        className="contents"
        onSubmit={(event) => {
          event.preventDefault();
          onSave();
        }}
      >
        <Field id="catalog-name" label="Name">
          <TextInput
            autoFocus
            maxLength={100}
            value={form.name}
            onChange={(event) => change({ name: event.target.value })}
          />
        </Field>
        {loadError && form.kind !== "main" && (
          <ErrorText>{loadError}</ErrorText>
        )}
        {form.kind === "cat" && (
          <Field id="catalog-main" label="Main category">
            <SearchSelect
              options={[
                { value: "", label: "No main category" },
                ...mains.map((main) => ({ value: main.id, label: main.name })),
              ]}
              value={form.link}
              onChange={(link) => change({ link })}
              onAdd={onAddLink}
            />
          </Field>
        )}
        {form.kind === "item" && (
          <Field id="catalog-category" label="Category">
            <SearchSelect
              options={categories.map((category) => ({
                value: category.id,
                label: category.name,
              }))}
              value={form.link}
              placeholder="Choose the category"
              onChange={(link) => change({ link })}
              onAdd={onAddLink}
            />
          </Field>
        )}
        {form.error && <ErrorText>{form.error}</ErrorText>}
      </form>
    </Dialog>
  );
}
