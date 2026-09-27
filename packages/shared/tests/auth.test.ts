import { describe, expect, it, vi } from "vitest";
import { AuthError, createAuthClient, pauseSeconds, validatePin } from "../src/index";

describe("AUTH-10/11 PIN rules shared by web and mobile", () => {
  it.each(["1111", "0000", "99999999", "1234", "4321", "01234567", "87654321", "123", "123456789", "１２３４", "58a6", "", "5826\n"])("rejects %j", (pin) => {
    expect(validatePin(pin)).not.toBeNull();
  });
  it.each(["5826", "6942", "0193", "1122", "58269104"])("accepts %j", (pin) => expect(validatePin(pin)).toBeNull());
});
it("pause countdown includes the last partial second and stops at zero", () => {
  expect(pauseSeconds(2000, 1001)).toBe(1);
  expect(pauseSeconds(2000, 2000)).toBe(0);
  expect(pauseSeconds(2000, 3000)).toBe(0);
});
it("typed client preserves challenge responses without inventing tokens", async () => {
  const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "verification_required" }), { status: 202 }));
  const result = await createAuthClient("/auth", fetcher)("sign-in", { email: "user@example.com", pin: "5826", deviceId: "phone" });
  expect(result.status).toBe("verification_required");
  expect(result.accessToken).toBeUndefined();
  expect(fetcher.mock.calls[0][0]).toBe("/auth/sign-in");
});
it("typed client exposes pause duration and handles empty rate-limit responses", async () => {
  const paused = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "paused", retryAfterSeconds: 900 }), { status: 423 }));
  await expect(createAuthClient("/auth", paused)("unlock", {})).rejects.toMatchObject({ response: { retryAfterSeconds: 900 }, httpStatus: 423 });
  const limited = vi.fn().mockResolvedValue(new Response(null, { status: 429 }));
  await expect(createAuthClient("/auth", limited)("sign-in", {})).rejects.toBeInstanceOf(AuthError);
});
it("explains an organization's longer minimum when a new PIN is too short", () => {
  expect(new AuthError({ status: "invalid_pin", minimumPinLength: 6 }, 400).message).toBe(
    "Use 6-8 digits, not all the same or an ascending/descending sequence.",
  );
  expect(new AuthError({ status: "invalid_pin", minimumPinLength: 4 }, 400).message).toBe(
    "Use 4-8 digits, not all the same or an ascending/descending sequence.",
  );
});
