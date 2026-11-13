export interface RankableOption {
  label: string;
  group?: string;
}

export function normalizeSearchText(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim();
}

const wordsOf = (text: string) => text.split(/[^\p{L}\p{N}]+/u);

function inOrder(letters: string, text: string): boolean {
  let at = 0;
  for (const letter of letters) {
    at = text.indexOf(letter, at) + 1;
    if (at === 0) return false;
  }
  return true;
}

// Lower is better; -1 hides the option.
function rankOf(query: string, option: RankableOption): number {
  const label = normalizeSearchText(option.label);
  if (label === query) return 0;
  if (label.startsWith(query)) return 1;
  if (wordsOf(label).some((word) => word.startsWith(query))) return 2;
  if (label.includes(query)) return 3;
  const text = `${label} ${normalizeSearchText(option.group ?? "")}`;
  if (query.split(" ").every((word) => text.includes(word))) return 4;
  if (inOrder(query.replace(/ /g, ""), label)) return 5;
  return -1;
}

// The options that match what was typed, best first: the exact label, then labels starting with it, labels with a
// word starting with it, labels containing it, options whose label and group hold every word typed, and last labels
// holding its letters in order. Equal matches keep their order; an empty query keeps every option.
export function rankOptions<T extends RankableOption>(
  query: string,
  options: readonly T[],
): T[] {
  const wanted = normalizeSearchText(query);
  if (!wanted) return [...options];
  return options
    .map((option, index) => ({ option, index, rank: rankOf(wanted, option) }))
    .filter((entry) => entry.rank >= 0)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.option);
}
