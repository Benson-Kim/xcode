import { fireEvent, render, screen } from "@testing-library/react-native";

import { Banner, ErrorText, Field, alpha } from "../src/ui";

it("announces an error as an assertive alert", async () => {
  await render(<ErrorText>Wrong PIN.</ErrorText>);
  expect(screen.getByRole("alert").props.accessibilityLiveRegion).toBe(
    "assertive",
  );
});

it("renders nothing for an empty error", async () => {
  await render(<ErrorText>{""}</ErrorText>);
  expect(screen.queryByRole("alert")).toBeNull();
});

it("gives the offline banner a status role and keeps the error banner an alert", async () => {
  await render(<Banner tone="offline">You are offline.</Banner>);
  expect(screen.getByRole("status").props.accessibilityLiveRegion).toBe(
    "polite",
  );
  expect(screen.queryByRole("alert")).toBeNull();

  await screen.rerender(<Banner>Something went wrong.</Banner>);
  expect(screen.getByRole("alert").props.accessibilityLiveRegion).toBe(
    "assertive",
  );
  expect(screen.queryByRole("status")).toBeNull();
});

it("ties a field's error to the input", async () => {
  const field = (error?: string, hint?: string) => (
    <Field
      label="Mobile number"
      value=""
      error={error}
      accessibilityHint={hint}
      onChangeText={() => {}}
    />
  );
  await render(field("Enter all 10 numbers."));
  expect(screen.getByLabelText("Mobile number").props.accessibilityHint).toBe(
    "Enter all 10 numbers.",
  );

  await screen.rerender(field(undefined, "Starts with 07 or 01."));
  expect(screen.getByLabelText("Mobile number").props.accessibilityHint).toBe(
    "Starts with 07 or 01.",
  );

  await screen.rerender(field());
  expect(
    screen.getByLabelText("Mobile number").props.accessibilityHint,
  ).toBeUndefined();
});

it("draws the focus ring from the brand colour", async () => {
  await render(
    <Field label="Mobile number" value="" onChangeText={() => {}} />,
  );
  const input = screen.getByLabelText("Mobile number");
  await fireEvent(input, "focus");
  expect(screen.getByLabelText("Mobile number")).toHaveStyle({
    outlineColor: "rgba(29, 95, 214, 0.35)",
  });
});

it.each([
  ["#1D5FD6", 0.35, "rgba(29, 95, 214, 0.35)"],
  ["#abc", 0.5, "#abc"],
  ["teal", 0.5, "teal"],
  ["rgb(1,2,3)", 0.5, "rgb(1,2,3)"],
])(
  "turns %s into a translucent colour only when it is #RRGGBB",
  (colour, opacity, expected) => {
    expect(alpha(colour, opacity)).toBe(expected);
  },
);
