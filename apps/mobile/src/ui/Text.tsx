import { Text as NativeText, StyleSheet, type TextProps } from "react-native";

import { fonts, useTheme } from "./theme";

type Weight = keyof typeof fonts;

// The person's text size preference scales every size and line height.
export function Text({
  weight = "regular",
  style,
  ...props
}: TextProps & { weight?: Weight }) {
  const { colors, fontScale } = useTheme();
  const flat = StyleSheet.flatten([
    {
      fontFamily: fonts[weight],
      color: colors.navy,
      fontSize: 16,
      lineHeight: 23,
    },
    style,
  ]);
  if (fontScale !== 1) {
    flat.fontSize = (flat.fontSize ?? 16) * fontScale;
    if (typeof flat.lineHeight === "number") flat.lineHeight *= fontScale;
  }
  return <NativeText {...props} style={flat} />;
}
