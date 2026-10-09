import { fireEvent, render, screen } from "@testing-library/react-native";
import { Linking } from "react-native";

import { checkForUpdate } from "../src/lib/updates";
import { UpdateNotice } from "../src/shell/UpdateBanner";

const source = {
  build: 41,
  manifestUrl:
    "https://github.com/Benson-Kim/xcode/releases/download/staging-android/version.json",
};

const manifest = (body: unknown, status = 200) =>
  jest.fn(async () => ({
    ok: status === 200,
    status,
    json: async () => body,
  })) as unknown as typeof fetch;

it("offers a newer build published on GitHub", async () => {
  const fetcher = manifest({
    build: 42,
    version: "1.0.0-staging.42",
    url: "https://github.com/x/apk",
  });
  expect(await checkForUpdate(source, fetcher)).toEqual({
    build: 42,
    version: "1.0.0-staging.42",
    url: "https://github.com/x/apk",
  });
  expect(String((fetcher as jest.Mock).mock.calls[0][0])).toMatch(
    /^https:\/\/github\.com\/Benson-Kim\/xcode\/releases\/download\/staging-android\/version\.json\?t=\d+$/,
  );
});

it.each([
  ["the same build", { build: 41, url: "https://github.com/x/apk" }],
  ["an older build", { build: 40, url: "https://github.com/x/apk" }],
  ["a build that is not a whole number", { build: 42.5, url: "https://x" }],
  ["a download that is not https", { build: 42, url: "http://github.com/x" }],
  ["no download", { build: 42 }],
])("offers nothing for %s", async (_, body) => {
  expect(await checkForUpdate(source, manifest(body))).toBeNull();
});

it("offers nothing when the file cannot be read", async () => {
  expect(await checkForUpdate(source, manifest({}, 404))).toBeNull();
  const failing = jest.fn(async () => {
    throw new TypeError("Network request failed");
  }) as unknown as typeof fetch;
  expect(await checkForUpdate(source, failing)).toBeNull();
});

it("never looks from a build made outside CI", async () => {
  const fetcher = manifest({ build: 99, url: "https://x" });
  expect(
    await checkForUpdate(
      { build: NaN, manifestUrl: source.manifestUrl },
      fetcher,
    ),
  ).toBeNull();
  expect(
    await checkForUpdate({ build: 41, manifestUrl: "" }, fetcher),
  ).toBeNull();
  expect(fetcher).not.toHaveBeenCalled();
});

it("shows the update; Update downloads it and Later hides it", async () => {
  const open = jest.spyOn(Linking, "openURL").mockResolvedValue(true);
  try {
    await render(
      <UpdateNotice
        source={source}
        fetcher={manifest({
          build: 42,
          version: "1.0.0-staging.42",
          url: "https://github.com/x/xcode-staging.apk",
        })}
      />,
    );
    expect(
      await screen.findByText(
        "A new version of XCODE is ready (1.0.0-staging.42).",
      ),
    ).toBeTruthy();
    await fireEvent.press(screen.getByRole("button", { name: "Update" }));
    expect(open).toHaveBeenCalledWith("https://github.com/x/xcode-staging.apk");
    await fireEvent.press(screen.getByRole("button", { name: "Later" }));
    expect(
      screen.queryByText("A new version of XCODE is ready (1.0.0-staging.42)."),
    ).toBeNull();
  } finally {
    open.mockRestore();
  }
});

it("shows nothing while the app is the newest build", async () => {
  await render(
    <UpdateNotice
      source={source}
      fetcher={manifest({ build: 41, url: "https://x" })}
    />,
  );
  await new Promise((resolve) => setTimeout(resolve, 0));
  expect(screen.queryByText(/A new version of XCODE/)).toBeNull();
});
