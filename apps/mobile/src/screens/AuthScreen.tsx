import {
  ActivityIndicator,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
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
  authenticated: "You’re signed in",
};

interface Props {
  screen: Screen;
  phoneNumber: string;
  pin: string;
  code: string;
  requested: boolean;
  busy: boolean;
  remaining: number;
  onPhoneNumber: (value: string) => void;
  onPin: (value: string) => void;
  onCode: (value: string) => void;
  onSubmit: () => void;
}
export function AuthScreen(props: Props) {
  const {
    screen,
    phoneNumber,
    pin,
    code,
    requested,
    busy,
    remaining,
    onPhoneNumber,
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

  function addDigit(digit: string) {
    if (!busy && pin.length < 8) onPin(`${pin}${digit}`);
  }

  function removeDigit() {
    if (!busy) onPin(pin.slice(0, -1));
  }

  const submitLabel = busy
    ? "Please wait"
    : changingPin && !requested
      ? "Send verification code"
      : screen === "unlock"
        ? "Unlock"
        : screen === "sign-in"
          ? "Sign in"
          : "Verify and continue";

  return (
    <View style={styles.form}>
      {(screen === "unlock" || showPin) && screen !== "sign-in" && (
        <View style={styles.who}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>{phoneNumber.trim().slice(-1) || "X"}</Text>
          </View>
          <Text style={styles.padTitle}>{screen === "unlock" ? "Unlock your phone" : changingPin ? "Choose a new PIN" : "Verify this device"}</Text>
          <Text style={styles.subtle}>{phoneNumber || "Your trusted account"}</Text>
        </View>
      )}
      {screen !== "unlock" && (
        <View style={styles.intro}>
          <Text style={styles.title}>{titles[screen]}</Text>
          <Text style={styles.subtle}>
            {screen === "sign-in"
              ? "Enter your mobile number, then your PIN."
              : "Complete this step to keep your account secure."}
          </Text>
        </View>
      )}
      {screen !== "unlock" && (
        <View style={styles.field}>
          <Text style={styles.label}>Mobile number</Text>
          <TextInput
            style={styles.input}
            accessibilityLabel="Mobile number"
            value={phoneNumber}
            onChangeText={onPhoneNumber}
            keyboardType="phone-pad"
            autoComplete="tel"
            editable={!busy && screen !== "verify-device" && !requested}
            placeholder="name@example.com"
            placeholderTextColor={COLORS.grey}
          />
        </View>
      )}
      {showPin && (
        <View style={styles.pinArea}>
          <TextInput
            style={styles.hiddenInput}
            accessibilityLabel={changingPin ? "New PIN" : "PIN"}
            value={pin}
            onChangeText={(value) => onPin(value.replace(/[^0-9]/g, ""))}
            secureTextEntry
            keyboardType="number-pad"
            maxLength={8}
            autoComplete="off"
            editable={!busy}
          />
          <Text style={styles.label}>{changingPin ? "New PIN" : "Enter your PIN"}</Text>
          <View accessibilityLabel={`${pin.length} of 4 numbers entered`} style={styles.dots}>
            {[0, 1, 2, 3].map((index) => (
              <View key={index} style={[styles.dot, pin.length > index && styles.dotFilled]} />
            ))}
          </View>
          {changingPin && <Text style={validatePin(pin) ? styles.error : styles.help}>{PIN_HELP}</Text>}
          <View style={styles.keypad}>
            {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((digit) => (
              <Pressable key={digit} accessibilityRole="button" accessibilityLabel={`Number ${digit}`} style={styles.key} onPress={() => addDigit(digit)}>
                <Text style={styles.keyText}>{digit}</Text>
              </Pressable>
            ))}
            <View />
            <Pressable accessibilityRole="button" accessibilityLabel="Number 0" style={styles.key} onPress={() => addDigit("0")}>
              <Text style={styles.keyText}>0</Text>
            </Pressable>
            <Pressable accessibilityRole="button" accessibilityLabel="Delete last number" style={styles.deleteKey} onPress={removeDigit}>
              <Text style={styles.deleteText}>⌫</Text>
            </Pressable>
          </View>
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
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={submitLabel}
        style={[styles.primary, busy && styles.busy]}
        onPress={onSubmit}
        disabled={
          busy ||
          !phoneNumber.trim() ||
          !validPin ||
          !validCode ||
          (remaining > 0 && (screen === "sign-in" || screen === "unlock"))
        }
      >
        {busy ? <ActivityIndicator color={COLORS.white} /> : <Text style={styles.primaryText}>{submitLabel}</Text>}
      </Pressable>
    </View>
  );
}

const COLORS = {
  cream: "#F6F3EC",
  navy: "#14213D",
  grey: "#4F5B6B",
  blue: "#1D5FD6",
  blueBusy: "#3F6FC9",
  line: "#CFC8B8",
  keyLine: "#DDD6C8",
  white: "#FFFFFF",
  red: "#B42318",
};

const styles = StyleSheet.create({
  form: { gap: 18 },
  intro: { gap: 6 },
  title: { fontSize: 26, lineHeight: 32, fontWeight: "700", color: COLORS.navy },
  field: { gap: 8 },
  label: { fontSize: 15, fontWeight: "600", color: COLORS.navy },
  input: {
    borderWidth: 1,
    borderColor: COLORS.line,
    borderRadius: 12,
    paddingHorizontal: 16,
    height: 56,
    fontSize: 18,
    color: COLORS.navy,
    backgroundColor: COLORS.white,
  },
  who: { alignItems: "center", gap: 6 },
  avatar: { width: 60, height: 60, borderRadius: 30, backgroundColor: COLORS.navy, alignItems: "center", justifyContent: "center" },
  avatarText: { color: COLORS.white, fontSize: 22, fontWeight: "700" },
  padTitle: { fontSize: 22, fontWeight: "700", color: COLORS.navy },
  subtle: { color: COLORS.grey, fontSize: 15, lineHeight: 21 },
  pinArea: { alignItems: "center", gap: 12 },
  hiddenInput: { position: "absolute", width: 1, height: 1, opacity: 0 },
  dots: { flexDirection: "row", gap: 18, height: 18 },
  dot: { width: 16, height: 16, borderRadius: 8, borderWidth: 2, borderColor: COLORS.navy },
  dotFilled: { backgroundColor: COLORS.navy },
  help: { color: COLORS.grey, textAlign: "center", fontSize: 13 },
  error: { color: COLORS.red, textAlign: "center", fontSize: 14 },
  keypad: { width: "100%", maxWidth: 320, display: "flex", flexDirection: "row", flexWrap: "wrap", gap: 12, justifyContent: "center" },
  key: { width: "30%", minWidth: 72, height: 60, borderWidth: 1, borderColor: COLORS.keyLine, borderRadius: 16, backgroundColor: COLORS.white, alignItems: "center", justifyContent: "center" },
  keyText: { fontSize: 26, fontWeight: "600", color: COLORS.navy },
  deleteKey: { width: "30%", minWidth: 72, height: 60, alignItems: "center", justifyContent: "center" },
  deleteText: { fontSize: 30, color: COLORS.navy },
  primary: { height: 56, borderRadius: 28, backgroundColor: COLORS.blue, alignItems: "center", justifyContent: "center" },
  busy: { backgroundColor: COLORS.blueBusy },
  primaryText: { color: COLORS.white, fontSize: 17, fontWeight: "600" },
});
