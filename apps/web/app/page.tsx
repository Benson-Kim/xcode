import { AuthPanel } from "../components/AuthPanel";

// Sign-in screens until there is a session, then the app shell.
export default function Home() {
  return <AuthPanel />;
}
