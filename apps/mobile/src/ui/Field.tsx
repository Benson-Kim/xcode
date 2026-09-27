import { forwardRef, useState } from "react";
import { StyleSheet, TextInput, View, type TextInputProps } from "react-native";
import { ErrorText } from "./Feedback";
import { Text } from "./Text";
import { fonts, useTheme } from "./theme";

type FieldProps = TextInputProps & {
  label: string;
  error?: string;
  digits?: boolean;
};

// A labelled input
export const Field = forwardRef<TextInput, FieldProps>(function Field(
  { label, error, digits, style, ...props },
  ref,
) {
  const { colors } = useTheme();
  const [focused, setFocused] = useState(false);
  const spaced = digits && Boolean(props.value);
  return (
    <View style={styles.field}>
      <Text weight="semibold" style={styles.label}>
        {label}
      </Text>
      <TextInput
        ref={ref}
        accessibilityLabel={label}
        placeholderTextColor={colors.grey}
        {...props}
        onFocus={(event) => {
          setFocused(true);
          props.onFocus?.(event);
        }}
        onBlur={(event) => {
          setFocused(false);
          props.onBlur?.(event);
        }}
        style={[
          styles.input,
          {
            borderColor: error
              ? colors.red
              : focused
                ? colors.blue
                : colors.line,
            borderWidth: error ? 2 : 1,
            color: colors.navy,
            backgroundColor: colors.white,
            // The design's soft focus ring, in place of the browser's own in the web preview.
            outlineStyle: "solid",
            outlineWidth: focused ? 3 : 0,
            outlineOffset: 1,
            outlineColor: `${colors.blue}59`,
          },
          spaced && styles.digits,
          style,
        ]}
      />
      {error ? <ErrorText>{error}</ErrorText> : null}
    </View>
  );
});

const styles = StyleSheet.create({
  field: { gap: 8 },
  label: { fontSize: 15 },
  input: {
    height: 56,
    paddingHorizontal: 16,
    borderRadius: 12,
    fontSize: 18,
    fontFamily: fonts.regular,
  },
  digits: { fontSize: 22, letterSpacing: 8 },
});
