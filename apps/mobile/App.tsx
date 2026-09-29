import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, AppState, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold, useFonts } from "@expo-google-fonts/figtree";
import { AppShell } from "./src/shell/AppShell";
import { fetchAppearance, forgetAppearance, loadSavedAppearance, pinPolicyOf, themeFor, type Appearance } from "./src/appearance";
import { AuthFlow } from "./src/auth/AuthFlow";
import { forgetThisPhone } from "./src/lib/api";
import { configureFormats } from "./src/lib/format";
import { loadPerson, loadSession, type StoredPerson } from "./src/lib/storage";
import { ThemeProvider } from "./src/ui";

type State =
  | { phase: "starting" }
  // trusted: the person this phone is trusted for, whose unlock pad opens; null for the sign-in screens.
  | { phase: "signed-out"; trusted: StoredPerson | null }
  | { phase: "signed-in"; person: StoredPerson; offline: boolean };

export default function App() {
  const [fontsLoaded, fontError] = useFonts({ Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold });
  const [state, setState] = useState<State>({ phase: "starting" });
  // The organization's branding, formats and the person's display preferences, as last saved on XCODE Web.
  const [appearance, setAppearance] = useState<Appearance | null>(null);

  useEffect(() => {
    let mounted = true;
    // A phone that kept a session for someone opens on their unlock pad, in their organization's brand.
    Promise.all([loadSession(), loadPerson(), loadSavedAppearance()])
      .then(([session, person, saved]) => {
        if (!mounted) return;
        setAppearance(saved);
        setState({ phase: "signed-out", trusted: session && person?.phoneNumber === session.phoneNumber ? person : null });
      })
      .catch(() => mounted && setState({ phase: "signed-out", trusted: null }));

    // Leaving the app locks it: coming back needs the PIN.
    const listener = AppState.addEventListener("change", (next) => {
      if (next !== "active") setState((current) => (current.phase === "signed-in" ? { phase: "signed-out", trusted: current.person } : current));
    });
    return () => {
      mounted = false;
      listener.remove();
    };
  }, []);

  // Settings saved on XCODE Web apply at the next sign in or unlock, which follows every return to the app.
  const signedIn = state.phase === "signed-in" && !state.offline;
  useEffect(() => {
    if (!signedIn) return;
    let active = true;
    fetchAppearance()
      .then((next) => {
        if (!active) return;
        setAppearance(next);
        // The next unlock, online or not, follows the organization's wrong-PIN policy.
        const policy = pinPolicyOf(next);
        if (policy) setState((current) => (current.phase === "signed-in" ? { ...current, person: { ...current.person, ...policy } } : current));
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [signedIn]);

  configureFormats(appearance?.formats);
  const theme = useMemo(() => themeFor(appearance), [appearance]);
  const brand = appearance && { name: appearance.branding.displayName, subline: appearance.organizationName, logo: appearance.branding.logo, logoAlt: appearance.branding.logoAlt };

  function forgotten() {
    setAppearance(null);
    void forgetAppearance();
  }

  const ready = state.phase !== "starting" && (fontsLoaded || fontError);
  return (
    <SafeAreaProvider>
      <ThemeProvider value={theme}>
        <SafeAreaView style={[styles.safe, { backgroundColor: theme.colors.cream }]} edges={state.phase === "signed-in" ? ["top", "left", "right"] : undefined}>
          {!ready ? (
            <View style={styles.starting}>
              <ActivityIndicator color={theme.colors.blue} accessibilityLabel="Starting XCODE" />
            </View>
          ) : state.phase === "signed-in" ? (
            <AppShell
              person={state.person}
              offline={state.offline}
              // Saved with the appearance, so it is the last business date the phone saw when it is offline.
              businessDate={appearance?.businessDate}
              onLock={() => setState({ phase: "signed-out", trusted: state.person })}
              onSessionEnded={() => setState({ phase: "signed-out", trusted: state.person })}
              onSwitchUser={async () => {
                await forgetThisPhone();
                forgotten();
                setState({ phase: "signed-out", trusted: null });
              }}
            />
          ) : (
            state.phase === "signed-out" && (
              <AuthFlow
                trusted={state.trusted}
                brand={brand ?? undefined}
                onSignedIn={(person, offline) => setState({ phase: "signed-in", person, offline })}
                onForgotten={forgotten}
              />
            )
          )}
        </SafeAreaView>
      </ThemeProvider>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  starting: { flex: 1, alignItems: "center", justifyContent: "center" },
});
