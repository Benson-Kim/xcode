import { createContext, useContext, type ReactNode } from "react";

// Colours that follow the organization's branding (primary, secondary, accent)
//  are read through useTheme() so a saved brand can replace them.
export const palette = {
  cream: "#F6F3EC",
  navy: "#14213D",
  brand: "#14213D",
  grey: "#4F5B6B",
  blue: "#1D5FD6",
  blueDark: "#1647A6",
  blueBusy: "#3F6FC9",
  blueTint: "#E8EFFC",
  blueWash: "#EEF3FD",
  line: "#CFC8B8",
  keyLine: "#DDD6C8",
  cardLine: "#E4DFD3",
  divider: "#EFEBE3",
  pressed: "#F3F0E8",
  field: "#FBF9F4",
  red: "#B42318",
  redBg: "#FDECEA",
  redLine: "#F3C1BB",
  redText: "#8A1C12",
  amberBg: "#FFF4DE",
  amberLine: "#E7C27A",
  amberText: "#6B4200",
  green: "#1E6B3A",
  greenBg: "#E3F1E8",
  white: "#FFFFFF",
  scrim: "rgba(20, 33, 61, 0.4)",
};

export type Palette = typeof palette;

export const fonts = {
  regular: "Figtree_400Regular",
  medium: "Figtree_500Medium",
  semibold: "Figtree_600SemiBold",
  bold: "Figtree_700Bold",
};

export type Theme = {
  colors: Palette;
  reducedMotion: boolean;
  fontScale: number;
};

export const defaultTheme: Theme = {
  colors: palette,
  reducedMotion: false,
  fontScale: 1,
};

const ThemeContext = createContext<Theme>(defaultTheme);

export function ThemeProvider({
  value,
  children,
}: {
  value: Theme;
  children: ReactNode;
}) {
  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  return useContext(ThemeContext);
}

// Mixes two #RRGGBB colours, like CSS color-mix(in srgb, colour amount%, towards).
export function mix(colour: string, amount: number, towards: string) {
  const channels = (hex: string) =>
    [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16));
  const [a, b] = [channels(colour), channels(towards)];
  return (
    "#" +
    a
      .map((value, index) =>
        Math.round((value * amount + b[index] * (100 - amount)) / 100),
      )
      .map((value) => value.toString(16).padStart(2, "0"))
      .join("")
      .toUpperCase()
  );
}
