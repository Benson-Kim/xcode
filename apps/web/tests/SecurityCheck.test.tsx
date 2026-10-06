import { fireEvent, renderHook, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { VehiclesPage } from "../components/setup";
import { authApi } from "../lib/api";
import { SecurityCheckError } from "../lib/checkedFetch";
import { apiRequest, useStreamedList } from "../lib/data";
import { withRetry } from "../lib/data/retry";
import { fetchWithSession, onSessionExpired, restoreSession } from "../lib/session";
import { renderInApp } from "./renderInApp";

afterEach(() => vi.unstubAllGlobals());

const MESSAGE = "A security check interrupted this request, so nothing was sent. Reload the page and try again.";
const challenge = () =>
  new Response("<html><title>One moment, please...</title></html>", { status: 200, headers: { "Content-Type": "text/html; charset=utf-8" } });
const json = (body: object, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const serve = (...answers: (() => Response)[]) => {
  const fetcher = vi.fn();
  answers.forEach((answer) => fetcher.mockImplementationOnce(async () => answer()));
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
};

it("rejects a GET that a security check answered, and does not retry it", async () => {
  const fetcher = serve(challenge, challenge, challenge);

  await expect(withRetry(() => apiRequest("setup/vehicles?page=1&pageSize=25"), new AbortController().signal)).rejects.toThrow(MESSAGE);

  expect(fetcher).toHaveBeenCalledOnce();
});

it("rejects a PUT that a security check answered, so a save cannot look successful", async () => {
  const fetcher = serve(challenge);

  const error = (await apiRequest("setup/vehicles/v-1", { method: "PUT", body: "{}" }).catch((reason) => reason)) as Error;

  expect(error).toBeInstanceOf(SecurityCheckError);
  expect(error.message).toBe(MESSAGE);
  expect(fetcher).toHaveBeenCalledOnce();
});

it("shows the message, not a TypeError, when the first page of a streamed list is intercepted", async () => {
  const fetcher = serve(challenge, challenge);

  const { result } = renderHook(() => useStreamedList("setup/vehicles"));

  await waitFor(() => expect(result.current.error).toBe(MESSAGE));
  expect(fetcher).toHaveBeenCalledOnce();
});

it("shows a clear message when a page has no list of items", async () => {
  serve(() => json({}));

  const { result } = renderHook(() => useStreamedList("setup/vehicles"));

  await waitFor(() => expect(result.current.error).toMatch(/not the list that was expected/));
});

it("rejects an auth call that a security check answered instead of reporting a failed sign-in", async () => {
  const fetcher = serve(challenge);

  await expect(authApi("sign-in", { phoneNumber: "0712345678", pin: "5826" })).rejects.toThrow(MESSAGE);

  expect(fetcher).toHaveBeenCalledOnce();
});

it("does not take an intercepted refresh for a success, and does not end the session", async () => {
  const fetcher = serve(() => json({}, 401), challenge, () => json({}));
  const expired = vi.fn();
  const stop = onSessionExpired(expired);

  await expect(fetchWithSession("/api/setup/vehicles")).rejects.toThrow(MESSAGE);

  stop();
  expect(fetcher.mock.calls.map(([input]) => input)).toEqual(["/api/setup/vehicles", "/api/auth/refresh"]);
  expect(expired).not.toHaveBeenCalled();
});

it("can refresh again after an intercepted refresh", async () => {
  const fetcher = serve(() => json({}, 401), challenge, () => json({}, 401), () => json({}), () => json({ ok: true }));

  await expect(fetchWithSession("/api/setup/vehicles")).rejects.toThrow(MESSAGE);
  const response = await fetchWithSession("/api/setup/vehicles");

  expect(response.status).toBe(200);
  expect(fetcher).toHaveBeenCalledTimes(5);
});

it("does not restore a session from an intercepted answer", async () => {
  serve(challenge);

  expect(await restoreSession()).toBe(false);
});

it("still restores a session from a JSON answer", async () => {
  serve(() => json({ firstName: "Test" }));

  expect(await restoreSession()).toBe(true);
});

it("still passes JSON, image and empty answers through", async () => {
  serve(
    () => json({ a: 1 }),
    () => new Response(null, { status: 204 }),
    () => new Response(new Uint8Array([137, 80, 78, 71]), { status: 200, headers: { "Content-Type": "image/png" } }),
    () => json({ title: "Invalid", detail: "Fix this." }, 400),
  );

  expect(await apiRequest("setup/people")).toEqual({ a: 1 });
  expect(await apiRequest("setup/people", { method: "DELETE" })).toEqual({});
  const image = await fetchWithSession("/api/setup/organization/logo");
  expect(image.headers.get("Content-Type")).toBe("image/png");
  await expect(apiRequest("setup/people")).rejects.toThrow("Fix this.");
});

const vehicle = {
  id: "v-1",
  registration: "KDA 482M",
  companyId: "company-1",
  companyName: "North Star",
  weeklyTarget: 15000,
  joinedOn: "2026-01-01",
  leftOn: null,
  active: true,
  targets: [],
  recurringItems: 0,
};

it("shows the message on the Vehicles page when its list is intercepted", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => challenge()));

  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] });

  expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
});

it("shows the message, not a saved toast, when a vehicle save is intercepted", async () => {
  const fetcher = vi.fn(async (input: string, init?: RequestInit) => {
    if (init?.method) return challenge();
    if (input.includes("company-options")) return json([{ id: "company-1", name: "North Star" }]);
    return json({ items: [vehicle], pageNumber: 1, pageSize: 25, total: 1 });
  });
  vi.stubGlobal("fetch", fetcher);
  renderInApp(<VehiclesPage />, { permissions: ["vehicles.manage"] });

  fireEvent.click(await screen.findByRole("button", { name: "KDA 482M" }));
  fireEvent.change(screen.getByLabelText("Weekly performance target"), { target: { value: "16000" } });
  fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

  expect(await screen.findByText(MESSAGE)).toBeInTheDocument();
  expect(screen.queryByText(/Changes saved/)).not.toBeInTheDocument();
  expect(fetcher).toHaveBeenCalledWith("/api/setup/vehicles/v-1", expect.objectContaining({ method: "PUT" }));
});
