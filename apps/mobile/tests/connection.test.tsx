import { render, screen } from "@testing-library/react-native";
import { Text } from "react-native";

import { wakeServer } from "../src/lib/api";
import { primeConnection, useConnected } from "../src/lib/network";
import { fakeApi } from "./fakeApi";

function Shown() {
  return <Text>{useConnected() ? "connected" : "offline"}</Text>;
}

it("wakes the server at most once a minute, and again after a wake that failed", async () => {
  const api = fakeApi();
  api.on("health/ready", [200, "Healthy"]);
  const start = Date.now() + 10 * 60_000;
  wakeServer(start);
  wakeServer(start + 30_000);
  await Promise.resolve();
  expect(api.calls.filter((call) => call.path === "health/ready")).toHaveLength(
    1,
  );

  api.on("health/ready", "offline");
  wakeServer(start + 61_000);
  await new Promise((resolve) => setTimeout(resolve, 0));
  wakeServer(start + 62_000);
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(api.calls.filter((call) => call.path === "health/ready")).toHaveLength(
    3,
  );
});

it("opens a banner on the connection the phone last reported, with no flash of the other one", async () => {
  require("expo-network").__setState({
    isConnected: true,
    isInternetReachable: true,
  });
  await primeConnection();
  const first = await render(<Shown />);
  expect(screen.getByText("connected")).toBeTruthy();
  await first.unmount();

  require("expo-network").__setState({
    isConnected: false,
    isInternetReachable: false,
  });
  await primeConnection();
  await render(<Shown />);
  expect(screen.getByText("offline")).toBeTruthy();
});
