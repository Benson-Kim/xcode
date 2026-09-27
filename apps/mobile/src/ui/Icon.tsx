import Svg, { Circle, Path, Rect } from "react-native-svg";

// Line icons (24 by 24, 2px stroke).
const shapes = {
  brand: (
    <>
      <Rect x="4" y="3" width="16" height="14" rx="2" />
      <Path d="M4 11h16" />
      <Path d="M8 17v3" />
      <Path d="M16 17v3" />
    </>
  ),
  lock: (
    <>
      <Rect x="4" y="11" width="16" height="10" rx="2" />
      <Path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </>
  ),
  backspace: (
    <>
      <Path d="M21 5H9l-7 7 7 7h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1z" />
      <Path d="M17 9l-6 6" />
      <Path d="M11 9l6 6" />
    </>
  ),
  alert: (
    <>
      <Circle cx="12" cy="12" r="10" />
      <Path d="M12 8v5" />
      <Path d="M12 16h.01" />
    </>
  ),
  offline: (
    <>
      <Path d="M2 2l20 20" />
      <Path d="M8.5 16.5a5 5 0 0 1 7 0" />
      <Path d="M5 12.5a10 10 0 0 1 5-2.7" />
      <Path d="M19 12.5a10 10 0 0 0-3-2.1" />
      <Path d="M12 20h.01" />
    </>
  ),
  home: (
    <>
      <Path d="M3 11l9-7 9 7" />
      <Path d="M5 10v10h14V10" />
    </>
  ),
  revenue: (
    <>
      <Rect x="2" y="6" width="20" height="12" rx="2" />
      <Circle cx="12" cy="12" r="2.5" />
    </>
  ),
  spend: (
    <>
      <Path d="M3 7h15a3 3 0 0 1 3 3v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <Path d="M3 7l12-4v4" />
      <Circle cx="16.5" cy="14" r="1" />
    </>
  ),
  more: (
    <>
      <Circle cx="5" cy="12" r="1.5" />
      <Circle cx="12" cy="12" r="1.5" />
      <Circle cx="19" cy="12" r="1.5" />
    </>
  ),
};

export type IconName = keyof typeof shapes;

export function Icon({
  name,
  size = 24,
  color,
}: {
  name: IconName;
  size?: number;
  color: string;
}) {
  return (
    <Svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke={color}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {shapes[name]}
    </Svg>
  );
}
