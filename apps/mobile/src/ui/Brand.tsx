import { Image, StyleSheet, View } from "react-native";
import { Icon } from "./Icon";
import { Text } from "./Text";
import { useTheme } from "./theme";

export function Brand({
  name = "XCODE",
  subline = "Fleet finance",
  logo,
  logoAlt,
}: {
  name?: string;
  subline?: string;
  logo?: string | null;
  logoAlt?: string;
}) {
  const { colors } = useTheme();
  return (
    <View style={styles.brand} accessibilityRole="header">
      {logo ? (
        <Image
          source={{ uri: logo }}
          accessibilityLabel={logoAlt || name}
          style={styles.logo}
          resizeMode="contain"
        />
      ) : (
        <View style={[styles.mark, { backgroundColor: colors.brand }]}>
          <Icon name="brand" size={20} color={colors.white} />
        </View>
      )}
      <View style={styles.names}>
        <Text weight="bold" numberOfLines={1} style={styles.name}>
          {name}
        </Text>
        <Text
          numberOfLines={1}
          style={[styles.subline, { color: colors.grey }]}
        >
          {subline}
        </Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  brand: { flexDirection: "row", alignItems: "center", gap: 10 },
  mark: {
    width: 38,
    height: 38,
    borderRadius: 10,
    alignItems: "center",
    justifyContent: "center",
  },
  logo: { width: 38, height: 38, borderRadius: 10 },
  names: { flexShrink: 1 },
  name: { fontSize: 18, lineHeight: 24, letterSpacing: 0.7 },
  subline: { fontSize: 13, lineHeight: 18 },
});
