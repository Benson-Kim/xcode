import type { PettyCashItemOption } from "@xcode/shared/pettyCash";

import type { SearchOption } from "../ui";

// Items as the options of a searchable select, kept together under their category in the order the categories first
// appear.
export function itemOptions(items: PettyCashItemOption[]): SearchOption[] {
  const groups = new Map<string, PettyCashItemOption[]>();
  for (const item of items)
    groups.set(item.categoryName, [
      ...(groups.get(item.categoryName) ?? []),
      item,
    ]);
  return [...groups].flatMap(([group, members]) =>
    members.map((item) => ({ value: item.id, label: item.name, group })),
  );
}
