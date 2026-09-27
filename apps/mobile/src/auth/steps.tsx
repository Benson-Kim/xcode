import type { ReactNode } from "react";
import { StyleSheet, View } from "react-native";
import {
  Banner,
  Button,
  DemoBox,
  Field,
  Icon,
  LinkButton,
  Text,
  useTheme,
} from "../ui";
import { LinkRow } from "./PinPad";

function Heading({ title, children }: { title: string; children?: ReactNode }) {
  const { colors } = useTheme();
  return (
    <View>
      <Text weight="bold" accessibilityRole="header" style={styles.h1}>
        {title}
      </Text>
      {children ? (
        <Text style={[styles.lead, { color: colors.grey }]}>{children}</Text>
      ) : null}
    </View>
  );
}

const DEMO_LOGINS = [
  "Owner: 0733 520 614, PIN 4826",
  "Revenue clerk: 0712 345 678, PIN 2580",
  "Office admin: 0722 410 355, PIN 1379",
  "Fleet manager: 0700 111 222, sets a PIN with an email code",
];

export function PhoneStep({
  value,
  error,
  banner,
  online,
  busy,
  onChange,
  onContinue,
  onFirstTime,
}: {
  value: string;
  error: string;
  banner: string;
  online: boolean;
  busy: boolean;
  onChange: (value: string) => void;
  onContinue: () => void;
  onFirstTime: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.screen}>
      <Heading title="Sign in">
        Enter the mobile number your admin registered for you. You will enter
        your PIN next.
      </Heading>
      {!online && (
        <Banner tone="offline">
          No internet. Signing in on this phone for the first time needs
          network.
        </Banner>
      )}
      <Field
        label="Mobile number"
        value={value}
        error={error}
        placeholder="0712 345 678"
        keyboardType="phone-pad"
        autoComplete="tel"
        textContentType="telephoneNumber"
        returnKeyType="next"
        autoFocus
        onChangeText={onChange}
        onSubmitEditing={onContinue}
      />
      {banner ? <Banner>{banner}</Banner> : null}
      <Button busy={busy} busyText="Checking…" onPress={onContinue}>
        Continue
      </Button>
      <Text style={[styles.small, { color: colors.grey, textAlign: "center" }]}>
        New here? Your admin adds you with your mobile number and email address.
      </Text>
      <LinkRow>
        <LinkButton align="start" disabled={busy} onPress={onFirstTime}>
          First time here? Set your PIN
        </LinkButton>
      </LinkRow>
      {__DEV__ && (
        <DemoBox>
          <Text weight="bold" style={styles.small}>
            Demo logins
          </Text>
          {DEMO_LOGINS.map((login) => (
            <Text key={login} style={[styles.small, { color: colors.grey }]}>
              {"• "}
              {login}
            </Text>
          ))}
          <Text style={[styles.small, { color: colors.grey }]}>
            A new phone asks for one email code, shown in the demo box.
          </Text>
        </DemoBox>
      )}
    </View>
  );
}

export function CodeStep({
  lead,
  email,
  value,
  error,
  busy,
  dead,
  resendIn,
  developmentCode,
  onChange,
  onConfirm,
  onResend,
  onCancel,
}: {
  lead: string;
  email: string;
  value: string;
  error: string;
  busy: boolean;
  dead: boolean;
  resendIn: number;
  developmentCode: string;
  onChange: (value: string) => void;
  onConfirm: () => void;
  onResend: () => void;
  onCancel: () => void;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.screen}>
      <Heading title="Check your email">
        {lead}We sent a code to{" "}
        {email ? <Text weight="semibold">{email}</Text> : "the email"}
        {email ? ", the email" : ""} your admin registered. It works for 10
        minutes.
      </Heading>
      <Field
        label="6 digit code"
        digits
        value={value}
        error={error}
        placeholder="6 numbers"
        keyboardType="number-pad"
        autoComplete="one-time-code"
        textContentType="oneTimeCode"
        maxLength={6}
        autoFocus
        onChangeText={onChange}
        onSubmitEditing={onConfirm}
      />
      <Button
        busy={busy}
        busyText="Checking…"
        disabled={dead}
        onPress={onConfirm}
      >
        Confirm code
      </Button>
      <LinkRow>
        <LinkButton
          align="start"
          disabled={busy || resendIn > 0}
          onPress={onResend}
        >
          {resendIn > 0 ? `Send a new code in ${resendIn}s` : "Send a new code"}
        </LinkButton>
        <LinkButton align="end" disabled={busy} onPress={onCancel}>
          Cancel
        </LinkButton>
      </LinkRow>
      <Text style={[styles.small, { color: colors.grey }]}>
        No email? Check your spam folder, or ask your admin to confirm your
        email address.
      </Text>
      {developmentCode ? (
        <DemoBox>
          <Text style={[styles.small, { color: colors.grey }]}>
            Demo only: your code is{" "}
            <Text weight="bold" style={[styles.small, { letterSpacing: 1.2 }]}>
              {`${developmentCode.slice(0, 3)} ${developmentCode.slice(3)}`}
            </Text>
          </Text>
        </DemoBox>
      ) : null}
    </View>
  );
}

export function PausedStep({
  remaining,
  busy,
  onReset,
  onSwitch,
}: {
  remaining: number;
  busy: boolean;
  onReset: () => void;
  onSwitch: () => void;
}) {
  const { colors } = useTheme();
  const clock = `${Math.floor(remaining / 60)}:${String(remaining % 60).padStart(2, "0")}`;
  return (
    <View style={styles.screen}>
      <View
        style={[styles.iconCircle, { backgroundColor: colors.redBg }]}
        aria-hidden
      >
        <Icon name="lock" size={26} color={colors.red} />
      </View>
      <Heading title="Sign in paused">
        Too many wrong PINs. Reset your PIN with an email code now, or try again
        in{" "}
        <Text weight="semibold" accessibilityRole="timer">
          {clock}
        </Text>
        . Nothing you captured has been lost.
      </Heading>
      <Button busy={busy} busyText="Sending…" onPress={onReset}>
        Reset PIN
      </Button>
      <Button tone="outline" disabled={busy} onPress={onSwitch}>
        Sign in as someone else
      </Button>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  h1: { fontSize: 26, lineHeight: 31 },
  lead: { marginTop: 6 },
  small: { fontSize: 14, lineHeight: 20 },
  iconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    alignItems: "center",
    justifyContent: "center",
  },
});
