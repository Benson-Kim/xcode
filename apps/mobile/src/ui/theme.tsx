import { createContext, useContext, type ReactNode } from "react";

// Colours that follow the organization's branding (primary, secondary, accent) are read through useTheme() so a saved brand can replace them.

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
  surface: "#FFFFFF",
  onBrand: "#FFFFFF",
  onFill: "#FFFFFF",
  scrim: "rgba(20, 33, 61, 0.4)",
};

export type Palette = typeof palette;

// The same design read against a dark surface, kept in step with :root[data-theme="dark"] in the web's globals.css.
export const darkPalette: Palette = {
  cream: "#0F1520",
  navy: "#E9EDF3",
  brand: "#223253",
  grey: "#A3AEBF",
  blue: "#7FA9F5",
  blueDark: "#A9C6F9",
  blueBusy: "#5C7FB8",
  blueTint: "#16202F",
  blueWash: "#131A26",
  line: "#394657",
  keyLine: "#2F3A48",
  cardLine: "#2B3542",
  divider: "#242D3A",
  pressed: "#202936",
  field: "#151C27",
  red: "#F0776B",
  redBg: "#2A1512",
  redLine: "#5E2A23",
  redText: "#FFB4A9",
  amberBg: "#2A2011",
  amberLine: "#5C4520",
  amberText: "#F6CE86",
  green: "#5FC183",
  greenBg: "#14291C",
  surface: "#1A222F",
  onBrand: "#FFFFFF",
  onFill: "#0F1520",
  scrim: "rgba(0, 0, 0, 0.6)",
};

export const fonts = {
  regular: "Figtree_400Regular",
  medium: "Figtree_500Medium",
  semibold: "Figtree_600SemiBold",
  bold: "Figtree_700Bold",
};

export type Theme = {
  colors: Palette;
  // Which palette is in use, for the few things a colour cannot say: the status bar's ink, mainly.
  dark: boolean;
  reducedMotion: boolean;
  fontScale: number;
};

export const defaultTheme: Theme = {
  colors: palette,
  dark: false,
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
