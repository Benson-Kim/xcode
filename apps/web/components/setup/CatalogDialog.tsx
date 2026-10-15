"use client";

import type { Dispatch, SetStateAction } from "react";

import type { ExpenseCategory, ExpenseMainCategory } from "../../lib/types";
import {
  Button,
  Dialog,
  ErrorText,
  Field,
  SelectInput,
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
  setForm,
  mains,
  categories,
  busy,
  onSave,
  onClose,
}: {
  form: CatalogForm;
  setForm: Dispatch<SetStateAction<CatalogForm | null>>;
  mains: ExpenseMainCategory[];
  categories: ExpenseCategory[];
  busy: boolean;
  onSave: () => void;
  onClose: () => void;
}) {
  const change = (next: Partial<CatalogForm>) =>
    setForm({ ...form, ...next, error: "" });
  return (
    <Dialog
      open
      size="sm"
      title={`${form.id ? "Edit" : "New"} ${KIND_NAMES[form.kind]}`}
      onClose={onClose}
      footer={
        <>
          <Button tone="outline" onClick={onClose}>
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
        {form.kind === "cat" && (
          <Field id="catalog-main" label="Main category">
            <SelectInput
              value={form.link}
              onChange={(event) => change({ link: event.target.value })}
            >
              <option value="">No main category</option>
              {mains.map((main) => (
                <option key={main.id} value={main.id}>
                  {main.name}
                </option>
              ))}
            </SelectInput>
          </Field>
        )}
        {form.kind === "item" && (
          <Field id="catalog-category" label="Category">
            <SelectInput
              value={form.link}
              onChange={(event) => change({ link: event.target.value })}
            >
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </SelectInput>
          </Field>
        )}
        {form.error && <ErrorText>{form.error}</ErrorText>}
      </form>
    </Dialog>
  );
}
