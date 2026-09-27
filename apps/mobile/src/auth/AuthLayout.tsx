import type { ReactNode } from "react";
import {
  ScrollView,
  StyleSheet,
  View,
  useWindowDimensions,
} from "react-native";
import { Brand, Text, useTheme } from "../ui";

export const VERSION = "XCODE Mobile v0.9";

export type BrandInfo = {
  name?: string;
  subline?: string;
  logo?: string | null;
  logoAlt?: string;
};

// The sign-in screens
export function AuthLayout({
  brand,
  footnote,
  children,
}: {
  brand?: BrandInfo;
  footnote?: string;
  children: ReactNode;
}) {
  const { colors } = useTheme();
  const { height } = useWindowDimensions();
  return (
    <ScrollView
      style={{ backgroundColor: colors.cream }}
      contentContainerStyle={[styles.app, height < 700 && styles.short]}
      keyboardShouldPersistTaps="handled"
    >
      <Brand
        name={brand?.name}
        subline={brand?.subline}
        logo={brand?.logo}
        logoAlt={brand?.logoAlt}
      />
      {children}
      <View style={styles.foot}>
        {footnote ? (
          <Text style={[styles.footText, { color: colors.grey }]}>
            {footnote}
          </Text>
        ) : null}
        <Text style={[styles.footText, { color: colors.grey }]}>{VERSION}</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  app: {
    flexGrow: 1,
    width: "100%",
    maxWidth: 420,
    alignSelf: "center",
    gap: 24,
    paddingTop: 28,
    paddingHorizontal: 24,
    paddingBottom: 20,
  },
  short: { gap: 16, paddingTop: 16 },
  foot: { marginTop: "auto", alignItems: "center" },
  footText: { fontSize: 13, lineHeight: 19, textAlign: "center" },
});
