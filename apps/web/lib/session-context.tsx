"use client";

import { createContext, useContext } from "react";

export type Session = {
  userId: string;
  firstName: string;
  lastName: string;
  role: string;
  permissions: string[];
};

type SessionState = { session: Session | null; can: (permission: string) => boolean };

const SessionContext = createContext<SessionState>({ session: null, can: () => false });

export const SessionProvider = SessionContext.Provider;

// Who is signed in and what they may do. `session` is null while it is still loading.
export function useSession() {
  return useContext(SessionContext);
}
