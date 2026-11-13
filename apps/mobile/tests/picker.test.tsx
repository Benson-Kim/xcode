import { fireEvent, render, screen } from "@testing-library/react-native";
import { readFileSync } from "fs";
import { join } from "path";

import { Picker, type Option } from "../src/pettycash/parts";

type RankVector = {
  name: string;
  query: string;
  options: (string | { label: string; group?: string })[];
  expected: string[];
};

const VECTORS = JSON.parse(
  readFileSync(
    join(
      __dirname,
      "../../../packages/shared/tests/fixtures/rank-options.json",
    ),
    "utf8",
  ),
) as RankVector[];

const radios = () =>
  screen
    .queryAllByRole("radio")
    .map((radio) => String(radio.props.accessibilityLabel).split(", ")[0]);

async function openAndType(
  options: Option[],
  query: string,
  onAdd?: () => void,
) {
  await render(
    <Picker
      label="Item"
      options={options}
      value=""
      onChange={() => {}}
      onAdd={onAdd}
    />,
  );
  await fireEvent.press(
    screen.getByRole("button", { name: "Item, not chosen" }),
  );
  await fireEvent.changeText(screen.getByLabelText("Search item"), query);
}

it.each(VECTORS)("ranks as the shared rule does: $name", async (vector) => {
  await openAndType(
    vector.options.map((option, index) => {
      const { label, group } =
        typeof option === "string"
          ? { label: option, group: undefined }
          : option;
      return { value: `o${index}`, label, sub: group };
    }),
    vector.query,
    () => {},
  );
  expect(radios()).toEqual(vector.expected);
});

it("offers no + Add new without onAdd", async () => {
  const many = Array.from({ length: 9 }, (_, index) => ({
    value: `v${index}`,
    label: `Item ${index}`,
  }));
  await openAndType(many, "zzz");
  expect(screen.getByText("Nothing matches.")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Add new item" })).toBeNull();
});

it("hands + Add new what was typed, as plain text, and closes the list", async () => {
  const onAdd = jest.fn();
  const typed = "  <b>Towing</b> ";
  await openAndType([{ value: "a", label: "Tyres" }], typed, onAdd);
  expect(screen.getByText("<b>Towing</b>")).toBeTruthy();
  await fireEvent.press(screen.getByRole("button", { name: "Add new item" }));
  expect(onAdd).toHaveBeenCalledWith("<b>Towing</b>");
  expect(screen.queryByLabelText("Search item")).toBeNull();
});
