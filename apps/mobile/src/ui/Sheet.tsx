import type { ReactNode } from "react";
import {
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useTheme } from "./theme";

// A sheet over the screen. A tap on the dimmed area outside it, or the system back, closes it, except while busy
// (a save is running), so an answer is never lost.
export function Sheet({
  busy = false,
  onClose,
  children,
}: {
  busy?: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const close = () => {
    if (!busy) onClose();
  };
  return (
    <Modal visible transparent animationType="slide" onRequestClose={close}>
      <KeyboardAvoidingView
        style={[styles.scrim, { backgroundColor: colors.scrim }]}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <Pressable
          accessible={false}
          importantForAccessibility="no"
          onPress={close}
          style={StyleSheet.absoluteFill}
        />
        <View
          accessibilityViewIsModal
          style={[styles.sheet, { backgroundColor: colors.surface }]}
        >
          <ScrollView
            keyboardShouldPersistTaps="handled"
            contentContainerStyle={[
              styles.content,
              { paddingBottom: 28 + insets.bottom },
            ]}
          >
            {children}
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: "flex-end" },
  sheet: {
    width: "100%",
    maxWidth: 420,
    maxHeight: "92%",
    alignSelf: "center",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
  },
  content: { gap: 14, padding: 20 },
});
