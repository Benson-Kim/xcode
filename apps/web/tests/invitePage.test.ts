import { afterEach, expect, it, vi } from "vitest";

import Invite from "../app/invite/page";

vi.mock("next/server", () => ({ connection: vi.fn(async () => undefined) }));

afterEach(() => {
  vi.unstubAllEnvs();
});

it("links only to https store pages, so a mistyped setting cannot become a script link", async () => {
  vi.stubEnv("APP_STORE_URL", "https://apps.apple.com/app/id1");
  vi.stubEnv("PLAY_STORE_URL", "javascript:alert(document.domain)");
  expect((await Invite()).props.stores).toEqual({
    appStore: "https://apps.apple.com/app/id1",
    playStore: undefined,
  });

  for (const value of [
    "http://play.google.com/store/apps/details?id=ke.co.priori.xcode",
    "data:text/html,<script>alert(1)</script>",
    " javascript:alert(1)",
    "not a url",
    "",
  ]) {
    vi.stubEnv("PLAY_STORE_URL", value);
    expect((await Invite()).props.stores.playStore).toBeUndefined();
  }
});
