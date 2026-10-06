import { fireEvent, render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { ErrorBoundary } from "../src/ui";

let crash = true;
function Fragile() {
  if (crash) throw new Error("render failed");
  return <Text>All good</Text>;
}

it("shows a fallback when a child throws and recovers on Try again", async () => {
  jest.spyOn(console, "error").mockImplementation(() => undefined);
  crash = true;
  await render(
    <ErrorBoundary>
      <Fragile />
    </ErrorBoundary>,
  );
  expect(screen.getByText("Something went wrong")).toBeTruthy();
  crash = false;
  await fireEvent.press(screen.getByRole("button", { name: "Try again" }));
  expect(screen.getByText("All good")).toBeTruthy();
});
