"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import {
  AuthError,
  inviteProblemText,
  isInviteToken,
} from "@xcode/shared/auth";
import { normalisePhone } from "@xcode/shared/format";

import { authApi } from "../lib/api";
import { SecurityCheckError } from "../lib/checkedFetch";
import { AuthFrame } from "./auth/AuthFrame";
import { NewPinFields, newPinProblem } from "./auth/NewPinFields";

export type StoreLinks = { appStore?: string; playStore?: string };

// "missing" for a link without a usable token, then the number and the PIN.
type Step = "missing" | "number" | "newpin" | "done";

// The link token sits in the fragment, so it never reaches a server log or a Referer.
function readLinkToken() {
  const raw = window.location.hash.slice(1);
  return isInviteToken(raw) ? raw : null;
}

// Once read, the fragment is taken off the address bar, so the token is not left in history or a copied URL.
function clearFragment() {
  if (window.location.hash)
    window.history.replaceState(
      window.history.state,
      "",
      window.location.pathname + window.location.search,
    );
}

const failureText = (error: unknown) =>
  error instanceof AuthError || error instanceof SecurityCheckError
    ? error.message
    : "Could not reach the service. Please try again.";

const onPhone = () => /Android|iPhone|iPad/.test(window.navigator.userAgent);

const openApp = () => window.location.replace("/");

type InvitePanelProps = { stores: StoreLinks; onSignedIn?: () => void };

export function InvitePanel({
  stores,
  onSignedIn = openApp,
}: InvitePanelProps) {
  const [token, setToken] = useState(readLinkToken);
  const [phoneScreen] = useState(onPhone);
  const [step, setStep] = useState<Step>(token ? "number" : "missing");
  const [phone, setPhone] = useState("");
  const [newPin, setNewPin] = useState("");
  const [repeatPin, setRepeatPin] = useState("");
  const [trust, setTrust] = useState(true);
  const [message, setMessage] = useState("");
  const [linkEnded, setLinkEnded] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    clearFragment();
    // A link pasted into this tab changes only the fragment, so the page does not reload.
    const takeNewLink = () => {
      const next = readLinkToken();
      clearFragment();
      if (!next) return;
      setToken(next);
      setMessage("");
      setLinkEnded(false);
      setStep("number");
    };
    window.addEventListener("hashchange", takeNewLink);
    return () => window.removeEventListener("hashchange", takeNewLink);
  }, []);

  async function run(work: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setMessage("");
    try {
      await work();
    } catch (error) {
      setMessage(failureText(error));
    } finally {
      setBusy(false);
    }
  }

  function confirmNumber() {
    const number = normalisePhone(phone);
    if (!/^0\d{9}$/.test(number))
      return setMessage("Enter your 10 digit mobile number.");
    setPhone(number);
    setLinkEnded(false);
    void run(async () => {
      try {
        const result = await authApi("invite/redeem", {
          token: token ?? "",
          phoneNumber: number,
        });
        if (result.status === "verification_required") {
          setNewPin("");
          setRepeatPin("");
          setStep("newpin");
        }
      } catch (error) {
        if (
          error instanceof AuthError &&
          error.response.status === "authentication_failed"
        ) {
          setLinkEnded(Boolean(error.response.inviteProblem));
          return setMessage(inviteProblemText(error.response.inviteProblem));
        }
        throw error;
      }
    });
  }

  function savePin() {
    const problem = newPinProblem(newPin, repeatPin);
    if (problem) return setMessage(problem);
    void run(async () => {
      try {
        const result = await authApi("pin/new", {
          phoneNumber: phone,
          purpose: "first_setup",
          code: "",
          pin: newPin,
          trustDevice: trust,
        });
        if (result.status === "authenticated") {
          setStep("done");
          onSignedIn();
        }
      } catch (error) {
        if (
          error instanceof AuthError &&
          error.response.status === "authentication_failed"
        ) {
          // The code the link minted ran out while the PIN was chosen: the link mints a fresh one.
          setStep("number");
          return setMessage("That took too long. Confirm your number again.");
        }
        throw error;
      }
    });
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (step === "number") confirmNumber();
    else if (step === "newpin") savePin();
  }

  const feedback = message && (
    <div className="ferr" role="alert">
      {message}
    </div>
  );
  return (
    <AuthFrame>
      <form onSubmit={submit} className="box" aria-labelledby="auth-title">
        {step === "missing" && <MissingLink />}
        {step === "number" && (
          <>
            <h1 id="auth-title">Set up XCODE</h1>
            <div className="sito">
              Confirm the mobile number you were invited with.
            </div>
            <div className="f">
              <label htmlFor="inPhone">Mobile number</label>
              <input
                className="inp num"
                id="inPhone"
                name="phoneNumber"
                inputMode="tel"
                autoComplete="tel"
                autoFocus
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
              />
            </div>
            {feedback}
            {linkEnded ? (
              <GoToSignIn />
            ) : (
              <button type="submit" className="btn ok" disabled={busy}>
                Continue
              </button>
            )}
          </>
        )}
        {step === "newpin" && (
          <>
            <h1 id="auth-title">Choose your PIN</h1>
            <NewPinFields
              newPin={newPin}
              repeatPin={repeatPin}
              onNewPin={setNewPin}
              onRepeatPin={setRepeatPin}
            />
            <label className="ck">
              <input
                type="checkbox"
                checked={trust}
                onChange={(event) => setTrust(event.target.checked)}
              />
              Trust this device
            </label>
            {feedback}
            <button type="submit" className="btn ok" disabled={busy}>
              Save and sign in
            </button>
          </>
        )}
        {step === "done" && <SignedIn />}
        {phoneScreen && <StoreBadges stores={stores} />}
      </form>
    </AuthFrame>
  );
}

function SignedIn() {
  return (
    <section aria-busy="true">
      <h1 id="auth-title">You are signed in</h1>
      <div className="muted">Opening XCODE...</div>
    </section>
  );
}

function MissingLink() {
  return (
    <>
      <h1 id="auth-title">Set up XCODE</h1>
      <div className="ferr" role="alert">
        This link is incomplete. Open it again from your invitation email, or
        sign in with the code in that email.
      </div>
      <GoToSignIn />
    </>
  );
}

function GoToSignIn() {
  return (
    <Link className="btn ok" href="/">
      Go to sign in
    </Link>
  );
}

// The app's store pages, when they are configured: no store images or scripts are loaded from elsewhere.
function StoreBadges({ stores }: { stores: StoreLinks }) {
  if (!stores.appStore && !stores.playStore) return null;
  return (
    <div className="silinks" aria-label="Get the app">
      <span className="muted">Get the app</span>
      {stores.appStore && (
        <a className="linkb" href={stores.appStore} rel="noopener noreferrer">
          App Store
        </a>
      )}
      {stores.playStore && (
        <a className="linkb" href={stores.playStore} rel="noopener noreferrer">
          Google Play
        </a>
      )}
    </div>
  );
}
