import { AuthError, type AuthStatus } from "@xcode/shared/auth";

import {
  expectStatus,
  failureMessage,
  isBlocked,
  isPaused,
  isPinLocked,
  isRefused,
  profileFailedMessage,
  type CheckedOperation,
} from "../src/auth/authErrors";
import {
  OfflineError,
  ServerError,
  ServerUnreachableError,
} from "../src/lib/api";

describe("failureMessage", () => {
  it("says no internet, in the words of the step", () => {
    expect(failureMessage(new OfflineError())).toBe(
      "No internet. Check your connection and try again.",
    );
    expect(
      failureMessage(
        new OfflineError(),
        "No internet. Sending a code needs network.",
      ),
    ).toBe("No internet. Sending a code needs network.");
  });

  it("keeps the server's own words, whatever the step says about the internet", () => {
    expect(
      failureMessage(new ServerUnreachableError(), "No internet. Try later."),
    ).toBe("Can't reach the XCODE server right now. Try again shortly.");
    expect(failureMessage(new ServerError(), "No internet. Try later.")).toBe(
      "Something went wrong on the server. Try again in a moment.",
    );
  });

  it.each([
    [
      429,
      { status: "authentication_failed" as const },
      "Too many requests. Please wait a minute.",
    ],
    [
      503,
      { status: "service_unavailable" as const },
      "The service is not available right now. Try again shortly.",
    ],
    [
      200,
      { status: "unexpected_response" as const },
      "The service answered in a way this app does not understand. Try again shortly.",
    ],
  ])("uses the AuthError text for a %i", (httpStatus, response, text) => {
    expect(failureMessage(new AuthError(response, httpStatus))).toBe(text);
  });

  it("does not show an unknown fault's own text", () => {
    expect(failureMessage(new Error("secret internals"))).toBe(
      "Something went wrong. Please try again.",
    );
  });
});

describe("profileFailedMessage", () => {
  it("asks for the PIN again only when a code was used up", () => {
    expect(profileFailedMessage(true)).toBe(
      "Signed in, but your profile could not be loaded. Enter your PIN to try again.",
    );
    expect(profileFailedMessage(false)).toBe(
      "Signed in, but your profile could not be loaded. Check your connection and try again.",
    );
  });
});

describe("expectStatus", () => {
  const allowed: [CheckedOperation, AuthStatus[]][] = [
    ["start", ["pin_required", "verification_required"]],
    ["pin", ["authenticated", "verification_required"]],
    ["code", ["authenticated", "code_verified", "code_resent"]],
    ["code/resend", ["verification_required"]],
    ["pin/forgot", ["verification_required"]],
    ["pin/new", ["authenticated"]],
  ];
  const every: AuthStatus[] = [
    "authenticated",
    "verification_required",
    "pin_required",
    "code_verified",
    "code_resent",
    "check_email",
    "pin_changed",
    "signed_out",
    "device_revoked",
  ];

  it.each(allowed)("lets %s answer only %j", (operation, statuses) => {
    for (const status of every) {
      if (statuses.includes(status))
        expect(expectStatus(operation, { status })).toEqual({ status });
      else
        expect(() => expectStatus(operation, { status })).toThrow(
          expect.objectContaining({
            response: { status: "unexpected_response" },
            httpStatus: 200,
          }),
        );
    }
  });

  it("returns the answer itself", () => {
    const answer = {
      status: "authenticated" as const,
      accessToken: "a",
      refreshToken: "r",
    };
    expect(expectStatus("pin", answer)).toBe(answer);
  });
});

describe("error kinds", () => {
  it("tells a pause and a refusal from other failures", () => {
    const paused = new AuthError({ status: "paused" }, 423);
    const refused = new AuthError({ status: "authentication_failed" }, 401);
    expect(isPaused(paused)).toBe(true);
    expect(isPaused(refused)).toBe(false);
    expect(isRefused(refused)).toBe(true);
    expect(isRefused(paused)).toBe(false);
    expect(isRefused(new Error("x"))).toBe(false);
  });

  it("tells a locked PIN and a blocked person apart", () => {
    const locked = new AuthError({ status: "pin_locked" }, 423);
    const blocked = new AuthError({ status: "blocked" }, 403);
    expect(isPinLocked(locked)).toBe(true);
    expect(isPinLocked(blocked)).toBe(false);
    expect(isBlocked(blocked)).toBe(true);
    expect(isBlocked(locked)).toBe(false);
    expect(isPaused(locked)).toBe(false);
  });
});
