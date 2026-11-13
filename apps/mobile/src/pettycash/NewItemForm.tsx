import { useState } from "react";
import { View } from "react-native";

import { SessionEndedError } from "../lib/api";
import { Button, ErrorText, Field, Sheet, Text } from "../ui";
import { getAllPages, sendTo, useLoaded } from "./client";
import { Picker, type Option } from "./parts";

type Category = { id: string; name: string; active?: boolean };

const CATEGORIES = "setup/expense-categories";

// The catalog's new item, opened from the item list with what was typed there. Saving hands the new item back to
// the expense as an option of its item list; cancelling, or a tap outside the sheet, goes back to it as it was.
export function NewItemForm({
  name,
  stamp,
  onSessionEnded,
  onCreated,
  onCancel,
}: {
  name: string;
  stamp: number;
  onSessionEnded: () => void;
  onCreated: (item: Option) => void;
  onCancel: () => void;
}) {
  const categories = useLoaded<Category[]>(
    CATEGORIES,
    stamp,
    onSessionEnded,
    getAllPages,
  );
  const [itemName, setItemName] = useState(name);
  const [categoryId, setCategoryId] = useState("");
  const [errors, setErrors] = useState<{ name?: string; category?: string }>(
    {},
  );
  const [problem, setProblem] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    const trimmed = itemName.trim();
    const found = {
      name: trimmed ? undefined : "Enter the item name.",
      category: categoryId ? undefined : "Choose the category.",
    };
    setErrors(found);
    if (found.name || found.category) return;
    setSaving(true);
    try {
      const outcome = await sendTo<{ id: string }>(
        "POST",
        `setup/expense-categories/${categoryId}/items`,
        { name: trimmed },
      );
      if (outcome.ok)
        onCreated({
          value: outcome.data.id,
          label: trimmed,
          sub:
            categories.data?.find((category) => category.id === categoryId)
              ?.name ?? "",
        });
      else setProblem(outcome.message);
    } catch (reason) {
      if (reason instanceof SessionEndedError) onSessionEnded();
      else setProblem("The request could not be completed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet busy={saving} onClose={onCancel}>
      <Text weight="bold" style={{ fontSize: 17 }}>
        New item
      </Text>
      <Field
        label="Item name"
        value={itemName}
        onChangeText={(text) => {
          setItemName(text);
          setErrors({ ...errors, name: undefined });
        }}
        error={errors.name}
        maxLength={100}
      />
      {categories.error ? <ErrorText>{categories.error}</ErrorText> : null}
      <Picker
        label="Category"
        options={(categories.data ?? [])
          .filter((category) => category.active !== false)
          .map((category) => ({ value: category.id, label: category.name }))}
        value={categoryId}
        onChange={(id) => {
          setCategoryId(id);
          setErrors({ ...errors, category: undefined });
        }}
        error={errors.category}
        empty={categories.loading ? "Loading categories." : undefined}
      />
      {problem ? <ErrorText>{problem}</ErrorText> : null}
      <View style={{ flexDirection: "row", gap: 12 }}>
        <Button tone="outline" onPress={onCancel}>
          Cancel
        </Button>
        <Button onPress={() => void save()} disabled={saving}>
          Save item
        </Button>
      </View>
    </Sheet>
  );
}
