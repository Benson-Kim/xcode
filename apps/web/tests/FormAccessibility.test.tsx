import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";

import { Choice, ChoiceField, Field, TextInput } from "../components/ui";

it("announces a field error and describes the input by it", () => {
  render(
    <Field id="x" label="X" error="Bad">
      <TextInput />
    </Field>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Bad");
  expect(screen.getByLabelText("X")).toHaveAccessibleDescription("Bad");
});

it("describes a choice group by its hint and error", () => {
  render(
    <ChoiceField label="Type" hint="Pick one" error="Required">
      <Choice type="radio" label="A" name="t" />
    </ChoiceField>,
  );
  expect(
    screen.getByRole("radiogroup", { name: "Type" }),
  ).toHaveAccessibleDescription("Pick one Required");
  expect(screen.getByRole("alert")).toHaveTextContent("Required");
});

it("leaves a choice group undescribed when it has neither hint nor error", () => {
  render(
    <ChoiceField label="Type">
      <Choice type="radio" label="A" name="t" />
    </ChoiceField>,
  );
  expect(screen.getByRole("radiogroup", { name: "Type" })).not.toHaveAttribute(
    "aria-describedby",
  );
});
