import { describe, expect, it, vi } from "vitest";

import {
  AuthError,
  createAuthClient,
  PIN_HELP,
  type AuthResponse,
} from "@xcode/shared/auth";

const answer = (body: unknown, status = 200) =>
  vi.fn().mockResolvedValue(
    new Response(typeof body === "string" ? body : JSON.stringify(body), {
      status,
    }),
  );

describe("auth client requests", () => {
  const request = { email: "user@example.com", pin: "5826", deviceId: "phone" };

  it("posts the request as JSON without credentials", async () => {
    const fetcher = answer({ status: "check_email" });
    await createAuthClient("/auth", fetcher)("sign-in", request);
    expect(fetcher.mock.calls[0]).toEqual([
      "/auth/sign-in",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(request),
      },
    ]);
  });

  it("sends the access token when there is one", async () => {
    const fetcher = answer({ status: "signed_out" });
    await createAuthClient("/auth", fetcher)("sign-out", {}, "abc");
    expect(fetcher.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer abc",
    });
  });

  it("sends no Authorization header for an empty token", async () => {
    const fetcher = answer({ status: "signed_out" });
    await createAuthClient("/auth", fetcher)("sign-out", {}, "");
    expect(fetcher.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
    });
  });

  it("joins the base address and the operation as given", async () => {
    const fetcher = answer({ status: "device_revoked" });
    await createAuthClient("https://api.test/x", fetcher)(
      "devices/42/revoke",
      {},
      "abc",
    );
    expect(fetcher.mock.calls[0][0]).toBe(
      "https://api.test/x/devices/42/revoke",
    );
  });

  it("turns a failing answer that is not JSON into a failed sign-in", async () => {
    const error = await createAuthClient(
      "/auth",
      answer("<html>bot check</html>", 502),
    )("sign-in", request).catch((reason: unknown) => reason);
    expect(error).toBeInstanceOf(AuthError);
    expect(error).toMatchObject({
      httpStatus: 502,
      response: { status: "authentication_failed" },
      message: "The service is not available right now. Try again shortly.",
    });
  });

  it("lets a network failure through unchanged", async () => {
    const offline = new TypeError("Failed to fetch");
    await expect(
      createAuthClient("/auth", vi.fn().mockRejectedValue(offline))(
        "sign-in",
        request,
      ),
    ).rejects.toBe(offline);
  });
});

describe("auth error messages", () => {
  it.each<[AuthResponse, number, string]>([
    [
      { status: "paused" },
      423,
      "Sign-in is paused. Try again when the timer ends, or reset your PIN.",
    ],
    [
      { status: "authentication_failed" },
      429,
      "Too many requests. Please wait a minute.",
    ],
    [
      { status: "authentication_failed" },
      401,
      "Authentication could not be completed. Check your details and try again.",
    ],
    [
      { status: "service_unavailable" },
      503,
      "The service is not available right now. Try again shortly.",
    ],
    [{ status: "invalid_pin" }, 400, PIN_HELP],
  ])("explains %o with HTTP %d", (response, httpStatus, message) => {
    const error = new AuthError(response, httpStatus);
    expect(error).toBeInstanceOf(Error);
    expect(error.message).toBe(message);
  });
});
