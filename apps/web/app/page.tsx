import { AuthPanel } from "../components/AuthPanel";

export default function Home() {
  return (
    <div className="page">
      <header className="brand">
        <span className="brand-mark" aria-hidden="true">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="4" y="3" width="16" height="14" rx="2" />
            <path d="M4 11h16" />
            <path d="M8 17v3" />
            <path d="M16 17v3" />
          </svg>
        </span>
        <span>
          <span className="brand-name">XCODE</span>
          <span className="brand-sub">Fleet finance</span>
        </span>
      </header>
      <main className="main">
        <AuthPanel />
        <p className="foot-note">New here? Your admin adds you with your mobile number and email address.</p>
        <p className="version">XCODE Web v0.9</p>
      </main>
      <p className="legal">Every sign in is recorded against your name. XCODE Web v0.9</p>
    </div>
  );
}
