import { createContext, useContext, type ReactNode } from "react";

import { darkTokens, lightTokens, nativePalette } from "@xcode/shared/tokens";

// Colours that follow the organization's branding (primary, secondary, accent) are read through useTheme() so a saved brand can replace them.

export const palette = nativePalette(lightTokens);

export type Palette = ReturnType<typeof nativePalette>;

export const darkPalette: Palette = nativePalette(darkTokens);

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

// rgba() for a #RRGGBB colour; anything else is returned unchanged rather than corrupted.
export function alpha(colour: string, opacity: number) {
  if (!/^#[0-9a-f]{6}$/i.test(colour)) return colour;
  const [r, g, b] = [1, 3, 5].map((start) =>
    parseInt(colour.slice(start, start + 2), 16),
  );
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}
