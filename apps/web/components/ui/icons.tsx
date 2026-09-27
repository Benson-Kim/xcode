import type { ComponentProps } from "react";

// Stroke icons from the design (24px grid, drawn at the size given).
function Icon({ size = 20, children, ...props }: ComponentProps<"svg"> & { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

export function BrandIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon {...props}>
      <rect x="4" y="3" width="16" height="14" rx="2" />
      <path d="M4 11h16" />
      <path d="M8 17v3" />
      <path d="M16 17v3" />
    </Icon>
  );
}

export function MenuIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon size={22} {...props}>
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </Icon>
  );
}

export function ChevronIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon size={16} {...props}>
      <path d="M6 9l6 6 6-6" />
    </Icon>
  );
}

export function CloseIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon {...props}>
      <path d="M6 6l12 12" />
      <path d="M18 6L6 18" />
    </Icon>
  );
}

export function AlertIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon size={16} {...props}>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v5" />
      <path d="M12 16h.01" />
    </Icon>
  );
}

export function OfflineIcon(props: ComponentProps<"svg"> & { size?: number }) {
  return (
    <Icon size={18} {...props}>
      <path d="M2 2l20 20" />
      <path d="M8.5 16.5a5 5 0 0 1 7 0" />
      <path d="M5 12.5a10 10 0 0 1 5-2.7" />
      <path d="M19 12.5a10 10 0 0 0-3-2.1" />
      <path d="M12 20h.01" />
    </Icon>
  );
}
