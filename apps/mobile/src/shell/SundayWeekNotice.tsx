import { useEffect, useState } from "react";
import { StyleSheet, View } from "react-native";

import {
  SUNDAY_WEEK_NOTICE_TITLE,
  sundayWeekNotice,
  sundayWeekNoticeDetail,
  type Appearance,
} from "@xcode/shared/appearance";

import { useFormats } from "../lib/formats";
import {
  loadSundayWeekDismissed,
  saveSundayWeekDismissed,
} from "../lib/storage";
import { LinkButton, Text, useTheme } from "../ui";

// v2.41 go-live: tells everyone signed in that the week now runs Sunday to Saturday, for seven days from the date the
// server moved it, until dismissed on this phone.
export function SundayWeekNotice({
  appearance,
}: {
  appearance: Appearance | null;
}) {
  const { colors } = useTheme();
  const { formatDateOnly } = useFormats();
  // Undefined until this phone's choice is read, so a notice already dismissed never flashes up.
  const [dismissed, setDismissed] = useState<string | null | undefined>();
  useEffect(() => {
    let active = true;
    loadSundayWeekDismissed()
      .then((value) => active && setDismissed(value ?? null))
      .catch(() => active && setDismissed(null));
    return () => {
      active = false;
    };
  }, []);
  const since =
    dismissed === undefined ? null : sundayWeekNotice(appearance, dismissed);
  if (!since) return null;

  function dismiss() {
    setDismissed(since);
    void saveSundayWeekDismissed(since!).catch(() => undefined);
  }

  return (
    <View
      accessible={false}
      role="status"
      accessibilityLiveRegion="polite"
      style={[
        styles.bar,
        { backgroundColor: colors.blueSoft, borderColor: colors.blueTint },
      ]}
    >
      <Text style={[styles.text, { color: colors.navy }]}>
        <Text weight="semibold" style={{ fontSize: 14, color: colors.navy }}>
          {SUNDAY_WEEK_NOTICE_TITLE}
        </Text>
        {` ${sundayWeekNoticeDetail(formatDateOnly(since))}`}
      </Text>
      <LinkButton onPress={dismiss}>Dismiss</LinkButton>
    </View>
  );
}

const styles = StyleSheet.create({
  bar: {
    flexDirection: "row",
    flexWrap: "wrap",
    alignItems: "center",
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  text: { flex: 1, minWidth: 180, fontSize: 14 },
});
