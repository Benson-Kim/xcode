import type { Metadata } from "next";
import { connection } from "next/server";

import { AuthFrame } from "../../components/auth/AuthFrame";

export const metadata: Metadata = {
  title: "Delete your XCODE account",
};

// Public, for the store listings: how a person has their account and personal details deleted, with or without the
// app. Rendered per request, like the sign-in page, so its scripts carry the nonce of this response's policy.
export default async function AccountDeletion() {
  await connection();
  return (
    <AuthFrame>
      <h1>Delete your XCODE account</h1>
      <p>
        Your XCODE account belongs to the organization that invited you.
        Deleting it ends your access and erases your personal details.
      </p>
      <section aria-labelledby="in-the-app" className="flex flex-col gap-2">
        <h2 id="in-the-app" className="font-bold">
          In the app
        </h2>
        <ol className="list-decimal pl-5">
          <li>Open Profile.</li>
          <li>Choose Delete my account.</li>
          <li>Confirm with your PIN.</li>
        </ol>
        <p>
          Your request goes to your organization&apos;s administrators, who
          complete it.
        </p>
      </section>
      <section
        aria-labelledby="without-the-app"
        className="flex flex-col gap-2"
      >
        <h2 id="without-the-app" className="font-bold">
          Without the app
        </h2>
        <p>
          Ask an administrator of your organization, such as the person who
          invited you, to delete your account. They do it from People in XCODE
          Web.
        </p>
      </section>
      <section aria-labelledby="deleted" className="flex flex-col gap-2">
        <h2 id="deleted" className="font-bold">
          What is deleted
        </h2>
        <p>
          Your name, phone number and email address are erased, and you can no
          longer sign in.
        </p>
      </section>
      <section aria-labelledby="kept" className="flex flex-col gap-2">
        <h2 id="kept" className="font-bold">
          What is kept
        </h2>
        <p>
          Records you entered for your organization, such as revenue and
          expenses, stay with it because it needs them for its accounts. They
          show &ldquo;Former member&rdquo; in place of your name.
        </p>
      </section>
    </AuthFrame>
  );
}
