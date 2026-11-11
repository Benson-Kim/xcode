import { randomBytes } from "crypto";

import { inviteTokenFrom } from "../src/auth/inviteLink";

const WEB = "https://xcode.example.com";
const token = randomBytes(32).toString("base64url");

describe("inviteTokenFrom", () => {
  it.each([
    `${WEB}/invite#${token}`,
    `${WEB}/invite/#${token}`,
    `${WEB}/invite?utm=mail#${token}`,
    `https://XCODE.example.com/invite#${token}`,
  ])("takes the token from %s", (url) => {
    expect(inviteTokenFrom(url, WEB)).toBe(token);
    expect(inviteTokenFrom(url, `${WEB}/`)).toBe(token);
  });

  it.each([
    ["another host", `https://xcode.example.com.evil.test/invite#${token}`],
    ["a look-alike host", `https://evil.test/invite#${token}`],
    ["plain http", `http://xcode.example.com/invite#${token}`],
    ["a port", `https://xcode.example.com:8443/invite#${token}`],
    ["another path", `${WEB}/invites#${token}`],
    ["a deeper path", `${WEB}/invite/more#${token}`],
    ["no fragment", `${WEB}/invite`],
    ["the token in the query", `${WEB}/invite?token=${token}`],
    ["a short token", `${WEB}/invite#${token.slice(1)}`],
    ["a token with other characters", `${WEB}/invite#${token.slice(1)}=`],
    ["two fragments", `${WEB}/invite#${token}#${token}`],
  ])("refuses %s", (_, url) => {
    expect(inviteTokenFrom(url, WEB)).toBeNull();
  });

  it("refuses every link when no web address is configured", () => {
    expect(inviteTokenFrom(`${WEB}/invite#${token}`, "")).toBeNull();
    expect(inviteTokenFrom(null, WEB)).toBeNull();
  });
});
