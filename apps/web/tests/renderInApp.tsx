import { render } from "@testing-library/react";
import type { ReactNode } from "react";

import { ToastProvider } from "../components/ui";
import { AppearanceProvider } from "../lib/appearance";
import { SessionProvider, type Session } from "../lib/session-context";
import { appearanceFixture } from "./fixtures";

export { appearanceFixture };

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
