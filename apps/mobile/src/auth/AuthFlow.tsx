import { useEffect, type ReactNode } from "react";

import { useOnline } from "../lib/network";
import type { StoredPerson } from "../lib/storage";
import { AuthLayout, type BrandInfo } from "./AuthLayout";
import { PadScreen } from "./PadScreen";
import { CodeStep, InviteStep, PausedStep, PhoneStep } from "./steps";
import { useAuthFlow } from "./useAuthFlow";

type Props = {
  // Who this phone is trusted for; the flow opens on their unlock pad.
  trusted: StoredPerson | null;
  brand?: BrandInfo;
  onSignedIn: (person: StoredPerson, offline: boolean) => void;
  // After "Not you?" or "Sign in as someone else" has made the phone forget the person.
  onForgotten?: () => void;
  // The token of an invitation link that opened the app, handed over once.
  invite?: string | null;
  onInviteTaken?: () => void;
};

export function AuthFlow({
  trusted,
  brand,
  onSignedIn,
  onForgotten,
  invite,
  onInviteTaken,
}: Props) {
  const online = useOnline();
  const { state, busy, actions } = useAuthFlow({
    trusted,
    onSignedIn,
    onForgotten,
  });
  const { screen } = state;
  const { openInvite } = actions;

  useEffect(() => {
    if (!invite) return;
    openInvite(invite);
    onInviteTaken?.();
  }, [invite, openInvite, onInviteTaken]);

  const layout = (content: ReactNode, footnote?: string) => (
    <AuthLayout brand={brand} footnote={footnote}>
      {content}
    </AuthLayout>
  );

  switch (screen.step) {
    case "phone":
      return layout(
        <PhoneStep
          value={state.phoneInput}
          error={screen.fieldError}
          banner={screen.banner}
          online={online}
          busy={busy}
          onChange={actions.editPhone}
          onContinue={actions.continueWithPhone}
        />,
      );
    case "invite":
      return layout(
        <InviteStep
          value={state.phoneInput}
          error={screen.fieldError}
          banner={screen.banner}
          trustedName={state.person?.firstName ?? ""}
          busy={busy}
          onChange={actions.editPhone}
          onContinue={actions.redeemInvite}
          onCancel={actions.cancelInvite}
        />,
      );
    case "code":
      return layout(
        <CodeStep
          lead={screen.lead}
          invitation={screen.invitation}
          email={screen.maskedEmail}
          value={screen.value}
          error={screen.error}
          busy={busy}
          dead={screen.dead}
          resendIn={screen.resendIn}
          developmentCode={screen.developmentCode}
          onChange={actions.typeCode}
          onConfirm={actions.confirmCode}
          onResend={actions.resend}
          onCancel={actions.cancelCode}
        />,
      );
    case "paused":
      return layout(
        <PausedStep
          remaining={screen.remaining}
          error={screen.error}
          busy={busy}
          onReset={actions.requestReset}
          onSwitch={actions.switchUser}
        />,
      );
    case "pad":
      return layout(
        <PadScreen
          state={state}
          screen={screen}
          busy={busy}
          actions={actions}
        />,
        screen.mode === "unlock"
          ? "PIN unlock works without internet."
          : undefined,
      );
  }
}
