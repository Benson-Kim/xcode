import type { ReactNode } from "react";

import { Brand } from "../Brand";

// The sign-in screen around its form: the brand on one side, the form on the other.
export function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <div className="signin min-h-screen">
      <header className="side">
        <Brand size={46} />
        <div className="cos">XCODE Web v2.33</div>
      </header>
      <main className="formside">
        <div className="box">{children}</div>
      </main>
    </div>
  );
}
