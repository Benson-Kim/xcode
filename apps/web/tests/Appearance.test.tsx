import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { AppShell } from "../components/AppShell";
import { OrganizationSettingsView } from "../components/OrganizationSettingsView";
import { AppearanceProvider, type Appearance } from "../lib/appearance";
import { configureFormats, kes } from "../lib/format";
import { ToastProvider } from "../components/ui";

const appearance = (overrides: Partial<Appearance["branding"]> = {}): Appearance => ({
  organizationName: "Demo Fleet",
  settingsVersion: 3,
  branding: { displayName: "North Star", logoAlt: "North Star", primary: "#0B5CAD", secondary: "#1B2A4A", accent: "#1E6B3A", logo: null, ...overrides },
  formats: { locale: "en-GB", timeZone: "UTC", datePattern: "medium", hour12: false, firstDayOfWeek: 1, weekNumbering: "iso8601", currency: "USD", useGroupping: true, numberDecimals: 2, direction: "ltr" },
  themeMode: "system",
  reducedMotion: true,
  fontScale: 1,
});

afterEach(() => configureFormats(null));

it("applies the organization's branding, formats and preferences across the app", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string) =>
      new Response(
        JSON.stringify(input.includes("appearance") ? appearance() : { userId: "me", firstName: "Test", lastName: "User", role: "Owner", permissions: [] }),
        { status: 200 },
      ),
    ),
  );
  render(<AppShell onSignOut={() => {}} />);

  expect(await screen.findByText("North Star")).toBeInTheDocument();
  expect(screen.getByText("Demo Fleet")).toBeInTheDocument();
  await waitFor(() => expect(document.documentElement.style.getPropertyValue("--color-blue")).toBe("#0B5CAD"));
  expect(document.documentElement.style.getPropertyValue("--color-brand")).toBe("#1B2A4A");
  expect(document.documentElement.dataset.reducedMotion).toBe("true");
  expect(document.title).toBe("North Star");
  expect(kes(1200)).toBe("USD 1,200");
});

const settings = {
  organization: { name: "Demo Fleet", slug: "demo-fleet" },
  localization: { locale: "en-GB", timeZone: "UTC", currency: "KES", datePattern: "medium", hour12: false, firstDayOfWeek: 1, weekNumbering: "iso8601", useGroupping: true, numberDecimals: 2, allowLocaleOverride: true, allowTimeZoneOverride: false, allowHour12Override: true, allowThemeOverride: true },
  branding: { displayName: "XCODE", legalName: "XCODE", logoAlt: "XCODE", primary: "#1D5FD6", secondary: "#14213D", accent: "#1E6B3A" },
  securityPolicy: { passwordMinLength: 12, passwordComplexity: true, passwordHistory: 5, pinLength: 4, lockoutThreshold: 5, lockoutMinutes: 15, accessTokenMinutes: 10, refreshTokenDays: 30, idleUnlockSeconds: 300, allowPinSignIn: true },
};

function renderSettings(refresh: () => void) {
  const fetcher = vi.fn(async (input: string, init?: RequestInit) =>
    new Response(JSON.stringify(init?.method ? { logo: "data:image/png;base64,AAAA" } : settings), { status: 200 }),
  );
  vi.stubGlobal("fetch", fetcher);
  render(
    <AppearanceProvider value={{ appearance: appearance(), loading: false, refresh }}>
      <ToastProvider>
        <OrganizationSettingsView />
      </ToastProvider>
    </AppearanceProvider>,
  );
  return fetcher;
}

it("shows saved brand changes straight away by refreshing the app's appearance", async () => {
  const refresh = vi.fn();
  const fetcher = renderSettings(refresh);
  fireEvent.change(await screen.findByLabelText("Display name"), { target: { value: "North Star" } });
  fireEvent.change(screen.getByLabelText("Primary colour"), { target: { value: "#0B5CAD" } });
  fireEvent.change(screen.getByLabelText("Reason for Brand"), { target: { value: "Refresh brand" } });
  fireEvent.click(screen.getByRole("button", { name: "Save brand" }));

  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  const put = fetcher.mock.calls.find(([input]) => input.endsWith("/branding"))!;
  expect(JSON.parse(String(put[1]!.body)).value).toMatchObject({ displayName: "North Star", primary: "#0B5CAD" });
});

it("uploads a logo from the settings page and shows it at once", async () => {
  const refresh = vi.fn();
  const fetcher = renderSettings(refresh);
  const input = (await screen.findByText("Upload logo")).querySelector("input")!;
  fireEvent.change(screen.getByLabelText("Reason for Brand"), { target: { value: "Replace logo" } });
  fireEvent.change(input, { target: { files: [new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "logo.png", { type: "image/png" })] } });

  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
  const put = fetcher.mock.calls.find(([path]) => path.endsWith("/organization/logo"))!;
  expect(put[1]!.method).toBe("PUT");
  expect(JSON.parse(String(put[1]!.body)).dataUrl).toMatch(/^data:image\/png;base64,/);
  expect(await screen.findByRole("status")).toHaveTextContent("Logo updated.");

  fireEvent.change(input, { target: { files: [new File(["<svg/>"], "logo.svg", { type: "image/svg+xml" })] } });
  expect(await screen.findByRole("alert")).toHaveTextContent("Upload a PNG, JPEG or WebP image.");
});
