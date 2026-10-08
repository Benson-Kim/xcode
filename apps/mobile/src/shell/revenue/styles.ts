import { StyleSheet } from "react-native";

// Styles used by more than one file in this folder.
export const styles = StyleSheet.create({
  list: { flex: 1 },
  content: {
    width: "100%",
    maxWidth: 420,
    alignSelf: "center",
    paddingTop: 28,
    paddingHorizontal: 24,
    paddingBottom: 32,
  },
  header: { gap: 16, marginBottom: 16 },
  detailHead: { minHeight: 0, paddingVertical: 6 },
  detailRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    minHeight: 60,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: "transparent",
  },
  detailDay: { width: 60, fontSize: 14 },
  detailNumber: { width: 92, fontSize: 14, textAlign: "right" },
  detailActual: { flex: 1, alignItems: "flex-end", gap: 4 },
  smallButton: { width: "auto", height: 44, paddingHorizontal: 16 },
});
