import { render } from "@testing-library/react";
import type { ReactNode } from "react";

import { ToastProvider } from "../components/ui";
import { AppearanceProvider, type Appearance } from "../lib/appearance";
import { SessionProvider, type Session } from "../lib/session-context";

// The appearance the app shell loads from /setup/appearance, with the organization's business date.
export function appearanceFixture(businessDate?: string): Appearance {
  return {
    organizationName: "Demo Fleet",
    settingsVersion: 1,
    businessDate,
    branding: {
      displayName: "XCODE",
      logoAlt: "XCODE",
      primary: "#1D5FD6",
      secondary: "#14213D",
      accent: "#1E6B3A",
      logo: null,
    },
    formats: {
      locale: "en-GB",
      timeZone: "UTC",
      datePattern: "medium",
      hour12: false,
      currency: "KES",
      useGroupping: true,
      numberDecimals: 2,
      firstDayOfWeek: 1,
      weekNumbering: "iso8601",
      direction: "ltr",
    },
    themeMode: "system",
    reducedMotion: false,
    fontScale: 1,
  };
}

// Renders a page inside the providers the app shell gives it: the signed-in session, the appearance (with its
// business date, when given) and toasts.
export function renderInApp(
  ui: ReactNode,
  session: Partial<Session> = {},
  options: { businessDate?: string } = {},
) {
  const value: Session = {
    userId: "me",
    firstName: "Test",
    lastName: "User",
    role: "Owner",
    permissions: [],
    ...session,
  };
  const appearance = options.businessDate
    ? appearanceFixture(options.businessDate)
    : null;
  return render(
    <SessionProvider
      value={{
        session: value,
        can: (permission) => value.permissions.includes(permission),
      }}
    >
      <AppearanceProvider
        value={{ appearance, loading: false, refresh: () => {} }}
      >
        <ToastProvider>{ui}</ToastProvider>
      </AppearanceProvider>
    </SessionProvider>,
  );
}
