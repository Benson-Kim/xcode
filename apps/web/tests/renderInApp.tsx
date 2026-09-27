import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import { SessionProvider, type Session } from "../lib/session-context";
import { ToastProvider } from "../components/ui";

// Renders a page inside the providers the app shell gives it: the signed-in session and toasts.
export function renderInApp(ui: ReactNode, session: Partial<Session> = {}) {
  const value: Session = { userId: "me", firstName: "Test", lastName: "User", role: "Owner", permissions: [], ...session };
  return render(
    <SessionProvider value={{ session: value, can: (permission) => value.permissions.includes(permission) }}>
      <ToastProvider>{ui}</ToastProvider>
    </SessionProvider>,
  );
}
