import { useEffect, useRef, useState } from "react";
import {
  AppState,
  ActivityIndicator,
  Pressable,
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
  const [phoneNumber, setPhoneNumber] = useState("");
  const [pin, setPin] = useState("");
  const [code, setCode] = useState("");
  const [requested, setRequested] = useState(false);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(true);
  const [pausedUntil, setPausedUntil] = useState(0);
  const [remaining, setRemaining] = useState(0);
  const [tab, setTab] = useState<"home" | "more">("home");

  const active = useRef(true);
  const authenticated = useRef(false);

  function navigate(next: Screen) {
    setScreen(next);
    setPin("");
    setCode("");
    setRequested(false);
    setMessage("");
    if (next === "authenticated") setTab("home");
  }

  useEffect(() => {
    let mounted = true;
    loadSession()
      .then((session) => {
        if (mounted && session) {
          setPhoneNumber(session.phoneNumber);
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
      const result = await authApi(operation, { phoneNumber, pin, code });

      if (
        result.status === "authenticated" &&
        result.accessToken &&
        result.refreshToken
      ) {
        await saveSession({
          phoneNumber,
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
          contentContainerStyle={[
            styles.container,
            screen === "authenticated" && styles.appContainer,
          ]}
          keyboardShouldPersistTaps="handled"
        >
          <View style={styles.brandRow}>
            <View style={styles.brandMark}>
              <Text style={styles.brandMarkText}>X</Text>
            </View>
            <View>
              <Text style={styles.brand}>XCODE</Text>
              <Text style={styles.brandSub}>Fleet finance</Text>
            </View>
          </View>
          {screen === "authenticated" ? (
            tab === "home" ? (
              <HomeView
                phoneNumber={phoneNumber}
                busy={busy}
                onLock={() => {
                  authenticated.current = false;
                  navigate("unlock");
                }}
              />
            ) : (
              <MoreView
                busy={busy}
                onLock={() => {
                  authenticated.current = false;
                  navigate("unlock");
                }}
                onRefresh={() => void execute("refresh")}
                onSignOut={() => void execute("sign-out")}
                onRevoke={() => void execute("revoke-device")}
              />
            )
          ) : (
            <>
              {busy && !phoneNumber && (
                <ActivityIndicator color={COLORS.blue} />
              )}
              <Text accessibilityRole="header" style={styles.title}>
                {titles[screen]}
              </Text>
              <AuthScreen
                screen={screen}
                phoneNumber={phoneNumber}
                pin={pin}
                code={code}
                requested={requested}
                busy={busy}
                remaining={remaining}
                onPhoneNumber={setPhoneNumber}
                onPin={setPin}
                onCode={setCode}
                onSubmit={submit}
              />
            </>
          )}
          {message ? (
            <Text accessibilityRole="alert" style={styles.message}>
              {message}
            </Text>
          ) : null}
          {screen !== "authenticated" && (
            <View style={styles.actions}>
              {screen !== "sign-in" && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Back to sign in"
                  disabled={busy}
                  onPress={() => navigate("sign-in")}
                >
                  <Text style={styles.link}>Back to sign in</Text>
                </Pressable>
              )}
              {screen !== "setup-pin" && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="First time here?"
                  disabled={busy}
                  onPress={() => navigate("setup-pin")}
                >
                  <Text style={styles.link}>First time here?</Text>
                </Pressable>
              )}
              {screen !== "pin-reset" && (
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Forgot PIN?"
                  disabled={busy}
                  onPress={() => navigate("pin-reset")}
                >
                  <Text style={styles.link}>Forgot PIN?</Text>
                </Pressable>
              )}
              {requested &&
                (screen === "setup-pin" || screen === "pin-reset") && (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Resend code (once per minute)"
                    disabled={busy}
                    onPress={() => void execute(`${screen}/request`)}
                  >
                    <Text style={styles.link}>
                      Resend code (once per minute)
                    </Text>
                  </Pressable>
                )}
            </View>
          )}
        </ScrollView>
        {screen === "authenticated" && <BottomNav tab={tab} onTab={setTab} />}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const COLORS = {
  cream: "#F6F3EC",
  navy: "#14213D",
  grey: "#4F5B6B",
  blue: "#1D5FD6",
  white: "#FFFFFF",
  line: "#E4DFD3",
};

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.cream },
  container: {
    padding: 24,
    paddingTop: 28,
    gap: 18,
    flexGrow: 1,
    maxWidth: 420,
    width: "100%",
    alignSelf: "center",
  },
  appContainer: { paddingBottom: 100 },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  brandMark: {
    width: 38,
    height: 38,
    borderRadius: 10,
    backgroundColor: COLORS.navy,
    alignItems: "center",
    justifyContent: "center",
  },
  brandMarkText: { color: COLORS.white, fontSize: 20, fontWeight: "800" },
  brand: {
    color: COLORS.navy,
    fontSize: 18,
    fontWeight: "700",
    letterSpacing: 1,
  },
  brandSub: { color: COLORS.grey, fontSize: 13 },
  title: {
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "700",
    color: COLORS.navy,
  },
  actions: { gap: 6, alignItems: "flex-start" },
  link: {
    minHeight: 44,
    paddingVertical: 12,
    color: COLORS.blue,
    fontSize: 15,
    fontWeight: "600",
  },
  message: {
    padding: 14,
    borderRadius: 12,
    backgroundColor: "#FDECEA",
    color: "#8A1C12",
    overflow: "hidden",
  },
  dashboard: { gap: 14 },
  homeHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  smallAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.navy,
    alignItems: "center",
    justifyContent: "center",
  },
  smallAvatarText: { color: COLORS.white, fontSize: 16, fontWeight: "700" },
  homeWho: { flex: 1, minWidth: 0 },
  homeName: {
    color: COLORS.navy,
    fontSize: 20,
    lineHeight: 24,
    fontWeight: "700",
  },
  homeRole: { color: COLORS.grey, fontSize: 14 },
  iconButton: {
    width: 44,
    height: 44,
    borderWidth: 1,
    borderColor: COLORS.line,
    borderRadius: 12,
    backgroundColor: COLORS.white,
    alignItems: "center",
    justifyContent: "center",
  },
  lockIcon: { color: COLORS.navy, fontSize: 24 },
  segment: {
    flexDirection: "row",
    padding: 4,
    borderRadius: 24,
    backgroundColor: "#EFEBE3",
    gap: 2,
  },
  segmentActive: {
    flex: 1,
    paddingVertical: 11,
    borderRadius: 20,
    backgroundColor: COLORS.white,
    color: COLORS.navy,
    textAlign: "center",
    fontSize: 14,
    fontWeight: "600",
  },
  segmentText: {
    flex: 1,
    paddingVertical: 11,
    color: COLORS.grey,
    textAlign: "center",
    fontSize: 14,
    fontWeight: "600",
  },
  scopeLabel: { color: COLORS.navy, fontSize: 14, fontWeight: "600" },
  scope: {
    height: 48,
    paddingHorizontal: 14,
    borderWidth: 1,
    borderColor: "#CFC8B8",
    borderRadius: 10,
    backgroundColor: COLORS.white,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  scopeText: { color: COLORS.navy, fontSize: 15 },
  chevron: { color: COLORS.grey, fontSize: 18 },
  card: {
    padding: 20,
    gap: 10,
    borderWidth: 1,
    borderColor: COLORS.line,
    borderRadius: 14,
    backgroundColor: COLORS.white,
  },
  cardTitle: { color: COLORS.navy, fontSize: 16, fontWeight: "700" },
  cardValue: {
    color: COLORS.navy,
    fontSize: 30,
    lineHeight: 35,
    fontWeight: "700",
  },
  cardNote: { color: COLORS.grey, fontSize: 14, lineHeight: 20 },
  progress: {
    height: 8,
    overflow: "hidden",
    borderRadius: 4,
    backgroundColor: "#EFEBE3",
  },
  progressFill: { height: 8, borderRadius: 4, backgroundColor: COLORS.blue },
  cardAction: {
    minHeight: 52,
    marginTop: 4,
    borderRadius: 26,
    backgroundColor: COLORS.blue,
    alignItems: "center",
    justifyContent: "center",
  },
  cardActionText: { color: COLORS.white, fontSize: 16, fontWeight: "600" },
  outlineAction: {
    minHeight: 52,
    borderWidth: 2,
    borderColor: COLORS.blue,
    borderRadius: 26,
    alignItems: "center",
    justifyContent: "center",
  },
  outlineText: { color: COLORS.blue, fontSize: 16, fontWeight: "600" },
  sectionTitle: {
    color: COLORS.navy,
    fontSize: 26,
    lineHeight: 32,
    fontWeight: "700",
  },
  version: { color: COLORS.grey, fontSize: 12, textAlign: "center" },
  bottomNav: {
    position: "absolute",
    left: 0,
    right: 0,
    bottom: 0,
    minHeight: 72,
    paddingBottom: 8,
    borderTopWidth: 1,
    borderTopColor: COLORS.line,
    backgroundColor: COLORS.white,
    flexDirection: "row",
  },
  navItem: {
    flex: 1,
    minHeight: 64,
    alignItems: "center",
    justifyContent: "center",
    gap: 3,
  },
  navActive: { borderTopWidth: 3, borderTopColor: COLORS.blue },
  navIcon: { color: COLORS.navy, fontSize: 20 },
  navLabel: { color: COLORS.grey, fontSize: 12, fontWeight: "600" },
});

function HomeView({
  phoneNumber,
  busy,
  onLock,
}: {
  phoneNumber: string;
  busy: boolean;
  onLock: () => void;
}) {
  return (
    <View style={styles.dashboard}>
      <View style={styles.homeHead}>
        <View style={styles.smallAvatar}>
          <Text style={styles.smallAvatarText}>
            {phoneNumber.slice(-1) || "X"}
          </Text>
        </View>
        <View style={styles.homeWho}>
          <Text style={styles.homeName}>Welcome back</Text>
          <Text style={styles.homeRole}>{phoneNumber}</Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Lock app"
          style={styles.iconButton}
          disabled={busy}
          onPress={onLock}
        >
          <Text style={styles.lockIcon}>⌑</Text>
        </Pressable>
      </View>
      <View style={styles.segment}>
        <Text style={styles.segmentActive}>Today</Text>
        <Text style={styles.segmentText}>This week</Text>
        <Text style={styles.segmentText}>This month</Text>
      </View>
      <Text style={styles.scopeLabel}>Data scope</Text>
      <View style={styles.scope}>
        <Text style={styles.scopeText}>All companies</Text>
        <Text style={styles.chevron}>⌄</Text>
      </View>
      <DashboardCard
        title="Revenue"
        value="KES 42,650"
        note="68% of today's target"
        progress={68}
      />
      <DashboardCard
        title="Today's capture"
        value="4 of 6 captured"
        note="2 vehicles still to capture"
        action="Capture revenue"
      />
      <DashboardCard
        title="Net contribution"
        value="KES 18,240"
        note="After running costs and commitments"
      />
      <Text style={styles.version}>XCODE Mobile v0.9</Text>
    </View>
  );
}

function DashboardCard({
  title,
  value,
  note,
  progress,
  action,
}: {
  title: string;
  value: string;
  note: string;
  progress?: number;
  action?: string;
}) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      <Text style={styles.cardValue}>{value}</Text>
      {progress ? (
        <View style={styles.progress}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
        </View>
      ) : null}
      <Text style={styles.cardNote}>{note}</Text>
      {action ? (
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={action}
          style={styles.cardAction}
        >
          <Text style={styles.cardActionText}>{action}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

function MoreView({
  busy,
  onLock,
  onRefresh,
  onSignOut,
  onRevoke,
}: {
  busy: boolean;
  onLock: () => void;
  onRefresh: () => void;
  onSignOut: () => void;
  onRevoke: () => void;
}) {
  return (
    <View style={styles.dashboard}>
      <Text style={styles.sectionTitle}>More</Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Account</Text>
        <Text style={styles.cardNote}>
          Manage your trusted phone and session.
        </Text>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Refresh session"
          disabled={busy}
          style={styles.outlineAction}
          onPress={onRefresh}
        >
          <Text style={styles.outlineText}>Refresh session</Text>
        </Pressable>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Revoke this phone's trust"
          disabled={busy}
          style={styles.outlineAction}
          onPress={onRevoke}
        >
          <Text style={styles.outlineText}>Revoke this phone's trust</Text>
        </Pressable>
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Lock app"
        disabled={busy}
        style={styles.outlineAction}
        onPress={onLock}
      >
        <Text style={styles.outlineText}>Lock app</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Sign out"
        disabled={busy}
        style={styles.outlineAction}
        onPress={onSignOut}
      >
        <Text style={styles.outlineText}>Sign out</Text>
      </Pressable>
      <Text style={styles.version}>XCODE Mobile v0.9</Text>
    </View>
  );
}

function BottomNav({
  tab,
  onTab,
}: {
  tab: "home" | "more";
  onTab: (tab: "home" | "more") => void;
}) {
  return (
    <View style={styles.bottomNav}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Home"
        accessibilityState={{ selected: tab === "home" }}
        style={[styles.navItem, tab === "home" && styles.navActive]}
        onPress={() => onTab("home")}
      >
        <Text style={styles.navIcon}>⌂</Text>
        <Text style={styles.navLabel}>Home</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="More"
        accessibilityState={{ selected: tab === "more" }}
        style={[styles.navItem, tab === "more" && styles.navActive]}
        onPress={() => onTab("more")}
      >
        <Text style={styles.navIcon}>•••</Text>
        <Text style={styles.navLabel}>More</Text>
      </Pressable>
    </View>
  );
}
