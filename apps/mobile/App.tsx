import { useEffect, useState } from "react";
import { ActivityIndicator, AppState, StyleSheet, View } from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import { Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold, useFonts } from "@expo-google-fonts/figtree";
import { AppShell } from "./src/shell/AppShell";
import { AuthFlow } from "./src/auth/AuthFlow";
import { forgetThisPhone } from "./src/lib/api";
import { loadPerson, loadSession, type StoredPerson } from "./src/lib/storage";
import { palette } from "./src/ui";

type State =
  | { phase: "starting" }
  // trusted: the person this phone is trusted for, whose unlock pad opens; null for the sign-in screens.
  | { phase: "signed-out"; trusted: StoredPerson | null }
  | { phase: "signed-in"; person: StoredPerson; offline: boolean };

export default function App() {
  const [fontsLoaded, fontError] = useFonts({ Figtree_400Regular, Figtree_500Medium, Figtree_600SemiBold, Figtree_700Bold });
  const [state, setState] = useState<State>({ phase: "starting" });

  useEffect(() => {
    let mounted = true;
    // A phone that kept a session for someone opens on their unlock pad.
    Promise.all([loadSession(), loadPerson()])
      .then(([session, person]) => mounted && setState({ phase: "signed-out", trusted: session && person?.phoneNumber === session.phoneNumber ? person : null }))
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

  const ready = state.phase !== "starting" && (fontsLoaded || fontError);
  return (
    <SafeAreaProvider>
      <SafeAreaView style={styles.safe} edges={state.phase === "signed-in" ? ["top", "left", "right"] : undefined}>
        {!ready ? (
          <View style={styles.starting}>
            <ActivityIndicator color={palette.blue} accessibilityLabel="Starting XCODE" />
          </View>
        ) : state.phase === "signed-in" ? (
          <AppShell
            person={state.person}
            offline={state.offline}
            onLock={() => setState({ phase: "signed-out", trusted: state.person })}
            onSessionEnded={() => setState({ phase: "signed-out", trusted: state.person })}
            onSwitchUser={async () => {
              await forgetThisPhone();
              setState({ phase: "signed-out", trusted: null });
            }}
          />
        ) : (
          state.phase === "signed-out" && <AuthFlow trusted={state.trusted} onSignedIn={(person, offline) => setState({ phase: "signed-in", person, offline })} />
        )}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: palette.cream },
  starting: { flex: 1, alignItems: "center", justifyContent: "center" },
});
