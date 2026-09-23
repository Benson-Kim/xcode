import { Button, StyleSheet, Text, TextInput, View } from "react-native";
import { PIN_HELP, validatePin } from "@xcode/shared";

export type Screen =
  | "sign-in"
  | "verify-device"
  | "setup-pin"
  | "pin-reset"
  | "unlock"
  | "authenticated";

export const titles: Record<Screen, string> = {
  "sign-in": "Sign in",
  "verify-device": "Verify this device",
  "setup-pin": "Set your first PIN",
  "pin-reset": "Reset your PIN",
  unlock: "Unlock your phone",
  authenticated: "You're signed in",
};

interface Props {
  screen: Screen;
  email: string;
  pin: string;
  code: string;
  requested: boolean;
  busy: boolean;
  remaining: number;
  onEmail: (value: string) => void;
  onPin: (value: string) => void;
  onCode: (value: string) => void;
  onSubmit: () => void;
}
export function AuthScreen(props: Props) {
  const {
    screen,
    email,
    pin,
    code,
    requested,
    busy,
    remaining,
    onEmail,
    onPin,
    onCode,
    onSubmit,
  } = props;

  const changingPin = screen === "setup-pin" || screen === "pin-reset";
  const showPin =
    screen === "sign-in" || screen === "unlock" || (changingPin && requested);
  const showCode = screen === "verify-device" || requested;
  const validPin =
    !showPin ||
    (changingPin ? validatePin(pin) === null : /^[0-9]{4,8}$/.test(pin));
  const validCode = !showCode || /^[0-9]{6}$/.test(code);

  return (
    <View style={styles.form}>
      <Text style={styles.label}>Email</Text>
      <TextInput
        style={styles.input}
        accessibilityLabel="Email"
        value={email}
        onChangeText={onEmail}
        keyboardType="email-address"
        autoCapitalize="none"
        autoComplete="email"
        editable={
          !busy &&
          screen !== "unlock" &&
          screen !== "verify-device" &&
          !requested
        }
      />
      {showPin && (
        <View style={styles.field}>
          <Text style={styles.label}>{changingPin ? "New PIN" : "PIN"}</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel={changingPin ? "New PIN" : "PIN"}
            value={pin}
            onChangeText={(value) => onPin(value.replace(/[^0-9]/g, ""))}
            secureTextEntry
            keyboardType="number-pad"
            maxLength={8}
            autoComplete="off"
            editable={!busy}
          />
          {changingPin && (
            <Text style={validatePin(pin) ? styles.error : undefined}>
              {PIN_HELP}
            </Text>
          )}
        </View>
      )}
      {showCode && (
        <View style={styles.field}>
          <Text style={styles.label}>Email verification code</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel="Email verification code"
            value={code}
            onChangeText={(value) => onCode(value.replace(/[^0-9]/g, ""))}
            keyboardType="number-pad"
            maxLength={6}
            autoComplete="one-time-code"
            editable={!busy}
          />
        </View>
      )}
      {remaining > 0 && (
        <Text accessibilityRole="alert" style={styles.error}>
          Sign-in paused. Try again in {Math.floor(remaining / 60)}:
          {String(remaining % 60).padStart(2, "0")}, or reset your PIN.
        </Text>
      )}
      <Button
        title={
          busy
            ? "Please wait…"
            : changingPin && !requested
              ? "Send verification code"
              : screen === "unlock"
                ? "Unlock"
                : screen === "sign-in"
                  ? "Sign in"
                  : "Verify and continue"
        }
        onPress={onSubmit}
        disabled={
          busy ||
          !email.trim() ||
          !validPin ||
          !validCode ||
          (remaining > 0 && (screen === "sign-in" || screen === "unlock"))
        }
      />
    </View>
  );
}
const styles = StyleSheet.create({
  form: { gap: 14 },
  field: { gap: 8 },
  label: { fontWeight: "600", color: "#0f172a" },
  input: {
    borderWidth: 1,
    borderColor: "#94a3b8",
    borderRadius: 8,
    padding: 14,
    fontSize: 18,
    color: "#0f172a",
    backgroundColor: "#fff",
  },
  error: { color: "#9f1239" },
});
