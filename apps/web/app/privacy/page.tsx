import type { Metadata } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { AuthFrame } from "../../components/auth/AuthFrame";

export const metadata: Metadata = {
  title: "XCODE privacy policy",
};

export const PRIVACY_CONTACT = "maina@priori.co.ke";
const UPDATED = "11 November 2026";

function Part({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section aria-labelledby={id} className="flex flex-col gap-2">
      <h2 id={id} className="font-bold">
        {title}
      </h2>
      {children}
    </section>
  );
}

// Public, for the store listings and anyone deciding whether to use XCODE. Rendered per request, like the sign-in
// page, so its scripts carry the nonce of this response's policy.
export default async function Privacy() {
  await connection();
  return (
    <AuthFrame>
      <h1>XCODE privacy policy</h1>
      <p>Last updated {UPDATED}.</p>
      <p>
        XCODE is fleet finance software from Priori Technologies Limited.
        Organizations use it to record the revenue and costs of their vehicles.
        The organization that invites you decides what is recorded about its
        work; Priori Technologies runs the service on its behalf.
      </p>
      <Part id="collected" title="What XCODE keeps">
        <ul className="list-disc pl-5">
          <li>
            Your account: name, phone number, email address, your role and the
            companies or vehicles you can see. Your organization&apos;s
            administrators enter these when they invite you.
          </li>
          <li>
            What you enter: revenue, expenses, petty cash and the other records
            of your organization, with who entered or changed them and when.
          </li>
          <li>
            Sign-in: your PIN, kept only as a one-way hash; one-time codes until
            they are used or expire; and the devices you trust, named by their
            browser or phone type, with when they were last used.
          </li>
          <li>
            Service logs: the time, outcome and a reference of each request, to
            keep the service secure and to fix faults. PINs, codes and sign-in
            tokens are never logged.
          </li>
          <li>
            Your network address, only to limit repeated sign-in attempts, for
            no more than a day.
          </li>
        </ul>
      </Part>
      <Part id="device" title="On your phone and in your browser">
        <p>
          The app keeps your sign-in and a check of your PIN in the phone&apos;s
          secure storage, on that phone only, together with records you saved
          offline until they are sent. Signing out or switching user removes
          them. The website uses only the cookies it needs to keep you signed
          in.
        </p>
      </Part>
      <Part id="not-done" title="What XCODE does not do">
        <p>
          No advertising, no analytics or tracking tools, and no selling or
          sharing of personal details for marketing. The app does not read your
          location, contacts, photos or camera.
        </p>
      </Part>
      <Part id="processors" title="Who handles it">
        <p>
          The service is hosted by DigitalOcean in Frankfurt, Germany, and by
          our web host. Invitations and sign-in codes are emailed through Amazon
          Web Services. Each handles the details only to run the service.
          Everything travels over encrypted connections.
        </p>
      </Part>
      <Part id="retention" title="How long it is kept">
        <p>
          Your details are kept while your account is active. When your account
          is deleted, your name, phone number and email address are erased.
          Records you entered stay with your organization, which needs them for
          its accounts, and show &ldquo;Former member&rdquo; in place of your
          name. Backups are replaced within 14 days.
        </p>
      </Part>
      <Part id="rights" title="Your choices">
        <p>
          You can ask to see, correct or delete your details through your
          organization&apos;s administrators, or by writing to us. You can
          delete your account in the app, as{" "}
          <a href="/account-deletion" className="underline">
            Delete your XCODE account
          </a>{" "}
          explains. Under Kenya&apos;s Data Protection Act, 2019, you may also
          complain to the Office of the Data Protection Commissioner.
        </p>
      </Part>
      <Part id="children" title="Children">
        <p>
          XCODE is for people working for an organization. It is not meant for
          children.
        </p>
      </Part>
      <Part id="contact" title="Contact">
        <p>
          Priori Technologies Limited:{" "}
          <a href={`mailto:${PRIVACY_CONTACT}`} className="underline">
            {PRIVACY_CONTACT}
          </a>
          . We will post changes to this policy on this page.
        </p>
      </Part>
    </AuthFrame>
  );
}
