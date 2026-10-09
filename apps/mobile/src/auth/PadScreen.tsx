import { LinkButton } from "../ui";
import type { AuthActions } from "./authActions";
import {
  isPersonalPad,
  padCopy,
  trustedHere,
  type AuthState,
  type PadScreen as Pad,
} from "./authFlowState";
import { LinkRow, PinPad } from "./PinPad";

type Props = {
  state: AuthState;
  screen: Pad;
  busy: boolean;
  actions: AuthActions;
};

function PersonalLinks({
  state,
  screen,
  busy,
  actions,
}: Props & { screen: Extract<Pad, { mode: "enter" | "unlock" }> }) {
  const known = trustedHere(state);
  return (
    <>
      <LinkRow>
        <LinkButton align="start" disabled={busy} onPress={actions.switchUser}>
          {screen.mode === "unlock" ? "Not you? Switch user" : "Not you?"}
        </LinkButton>
        <LinkButton align="end" disabled={busy} onPress={actions.requestReset}>
          Forgot PIN?
        </LinkButton>
      </LinkRow>
      {/* PINs are 4 numbers unless an organization asks for more. A phone that has not signed in
          before cannot know, so a longer PIN is typed in full and sent with Continue. */}
      {screen.longPin ? (
        <LinkRow>
          <LinkButton
            align="start"
            disabled={busy || screen.pin.length < 4}
            onPress={actions.submitLongPin}
          >
            Continue
          </LinkButton>
        </LinkRow>
      ) : (
        screen.mode === "enter" &&
        !known &&
        state.pinLength === 4 && (
          <LinkRow>
            <LinkButton
              align="start"
              disabled={busy}
              onPress={actions.chooseLongPin}
            >
              My PIN has more than 4 numbers
            </LinkButton>
          </LinkRow>
        )
      )}
    </>
  );
}

export function PadScreen({ state, screen, busy, actions }: Props) {
  const copy = padCopy(state, screen);
  return (
    <PinPad
      header={copy.header}
      label={copy.label}
      length={copy.length}
      value={screen.pin}
      error={screen.error}
      status={busy && screen.checking ? copy.checking : ""}
      busy={busy}
      shake={state.shake}
      onDigit={actions.press}
      onDelete={actions.backspace}
      links={
        isPersonalPad(screen) ? (
          <PersonalLinks
            state={state}
            screen={screen}
            busy={busy}
            actions={actions}
          />
        ) : screen.mode === "confirm" ? (
          <LinkRow>
            <LinkButton
              align="start"
              disabled={busy}
              onPress={actions.startAgain}
            >
              Start again
            </LinkButton>
          </LinkRow>
        ) : null
      }
    />
  );
}
