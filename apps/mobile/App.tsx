import { useEffect, useRef, useState } from "react";
import {
  AppState,
  Button,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";

import {
  AuthError,
  pauseSeconds,
  validatePin,
  type AuthOperation,
} from "@xcode/shared";
import { authApi } from "./src/api";
import { clearSession, loadSession, saveSession } from "./src/storage";
import { AuthScreen, titles, type Screen } from "./src/screens/AuthScreen";

export default function App() {
  const [screen, setScreen] = useState<Screen>("sign-in");
  const [email, setEmail] = useState("");
  const [pin, setPin] = useState("");
  const [code, setCode] = useState("");
  const [requested, setRequested] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(true);
  const [pausedUntil, setPausedUntil] = useState(0);
  const [remaining, setRemaining] = useState(0);

  const active = useRef(true);
  const authenticated = useRef(false);

  function navigate(next: Screen) {
    setScreen(next);
    setPin("");
    setCode("");
    setRequested(false);
    setMessage("");
  }

  useEffect(() => {
    let mounted = true;
    loadSession()
      .then((session) => {
        if (mounted && session) {
          setEmail(session.email);
          setScreen("unlock");
        }
      })
      .catch(() => {
        if (mounted)
          setMessage(
            "Secure storage could not be opened. Unlock your device and retry.",
          );
      })
      .finally(() => {
        if (mounted) setBusy(false);
      });

    const listener = AppState.addEventListener("change", (state) => {
      active.current = state === "active";

      if (!active.current) {
        setPin("");
        setCode("");
        if (authenticated.current) {
          authenticated.current = false;
          setScreen("unlock");
        }
      }
    });

    return () => {
      mounted = false;
      listener.remove();
    };
  }, []);

  useEffect(() => {
    const tick = () => setRemaining(pauseSeconds(pausedUntil));
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [pausedUntil]);

  async function execute(operation: AuthOperation | "revoke-device") {
    setBusy(true);
    setMessage("");
    try {
      const result = await authApi(operation, { email, pin, code });

      if (
        result.status === "authenticated" &&
        result.accessToken &&
        result.refreshToken
      ) {
        await saveSession({
          email,
          accessToken: result.accessToken,
          refreshToken: result.refreshToken,
        });

        authenticated.current = active.current;
        navigate(active.current ? "authenticated" : "unlock");
        setPausedUntil(0);
      } else if (result.status === "verification_required") {
        authenticated.current = false;
        navigate("verify-device");
        setMessage(
          "Enter your email code within 10 minutes to trust this device.",
        );
      } else if (result.status === "check_email") {
        setRequested(true);
        setMessage(
          "If this account is eligible, a code has been sent to your email.",
        );
      } else if (
        result.status === "signed_out" ||
        result.status === "device_revoked"
      ) {
        await clearSession();
        authenticated.current = false;
        navigate("sign-in");
      }
    } catch (error) {
      if (error instanceof AuthError) {
        if (error.response.retryAfterSeconds)
          setPausedUntil(Date.now() + error.response.retryAfterSeconds * 1000);

        if (operation === "refresh" && error.httpStatus === 401) {
          await clearSession();
          authenticated.current = false;
          navigate("sign-in");
        }
        setMessage(error.message);
      } else
        setMessage(
          "Could not complete the request. Check your connection and secure storage, then retry.",
        );
    } finally {
      setBusy(false);
    }
  }

  function submit() {
    const changingPin = screen === "setup-pin" || screen === "pin-reset";

    if (changingPin && requested && validatePin(pin)) {
      setMessage(validatePin(pin)!);
      return;
    }
    const operation = changingPin
      ? (`${screen}/${requested ? "complete" : "request"}` as AuthOperation)
      : (screen as AuthOperation);
    void execute(operation);
  }

  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe}>
        <ScrollView
          contentContainerStyle={styles.container}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={styles.brand}>XCODE</Text>
          <Text accessibilityRole="header" style={styles.title}>
            {titles[screen]}
          </Text>
          {screen === "authenticated" ? (
            <View style={styles.actions}>
              <Text>Signed in as {email}.</Text>
              <Button
                title="Lock app"
                disabled={busy}
                onPress={() => {
                  authenticated.current = false;
                  navigate("unlock");
                }}
              />
              <Button
                title="Refresh session"
                disabled={busy}
                onPress={() => void execute("refresh")}
              />
              <Button
                title="Revoke this phone's trust"
                disabled={busy}
                onPress={() => void execute("revoke-device")}
              />
              <Button
                title="Sign out"
                disabled={busy}
                onPress={() => void execute("sign-out")}
              />
            </View>
          ) : (
            <AuthScreen
              screen={screen}
              email={email}
              pin={pin}
              code={code}
              requested={requested}
              busy={busy}
              remaining={remaining}
              onEmail={setEmail}
              onPin={setPin}
              onCode={setCode}
              onSubmit={submit}
            />
          )}
          {message ? (
            <Text accessibilityRole="alert" style={styles.message}>
              {message}
            </Text>
          ) : null}
          {screen !== "authenticated" && (
            <View style={styles.actions}>
              {screen !== "sign-in" && (
                <Button
                  title="Back to sign in"
                  disabled={busy}
                  onPress={() => navigate("sign-in")}
                />
              )}
              {screen !== "setup-pin" && (
                <Button
                  title="First time? Set up PIN"
                  disabled={busy}
                  onPress={() => navigate("setup-pin")}
                />
              )}
              {screen !== "pin-reset" && (
                <Button
                  title="Forgot PIN?"
                  disabled={busy}
                  onPress={() => navigate("pin-reset")}
                />
              )}
              {requested &&
                (screen === "setup-pin" || screen === "pin-reset") && (
                  <Button
                    title="Resend code (once per minute)"
                    disabled={busy}
                    onPress={() => void execute(`${screen}/request`)}
                  />
                )}
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: "#f1f5f9" },
  container: {
    padding: 24,
    gap: 24,
    flexGrow: 1,
    justifyContent: "center",
    maxWidth: 520,
    width: "100%",
    alignSelf: "center",
  },
  brand: { color: "#0369a1", fontWeight: "700", letterSpacing: 3 },
  title: { fontSize: 30, fontWeight: "700", color: "#0f172a" },
  actions: { gap: 16 },
  message: {
    padding: 14,
    borderRadius: 8,
    backgroundColor: "#e2e8f0",
    color: "#0f172a",
  },
});
