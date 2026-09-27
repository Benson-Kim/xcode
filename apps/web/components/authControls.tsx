import type { ComponentProps, ReactNode } from "react";
import { AlertIcon, cn } from "./ui";
import { Brand } from "./Brand";

// The sign-in screens use the design's larger controls: 56px fields (52px from 720px up) and full-width buttons.

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center gap-2.5 px-6 pt-8 min-[720px]:px-12 min-[720px]:pt-7">
        <Brand />
      </header>
      <main className="flex flex-1 flex-col px-6 pt-7 pb-4 min-[720px]:items-center min-[720px]:justify-center min-[720px]:gap-5 min-[720px]:pt-6 min-[720px]:pb-10">
        <div className="w-full min-[720px]:w-110 min-[720px]:rounded-[20px] min-[720px]:border min-[720px]:border-card-line min-[720px]:bg-white min-[720px]:p-10 min-[720px]:shadow-panel">
          {children}
        </div>
        <p className="mt-auto mb-0 pt-6 text-center text-sm text-grey min-[720px]:m-0 min-[720px]:pt-0">
          New here? Your admin adds you with your mobile number and email address.
        </p>
        <p className="mt-2 mb-0 text-center text-xs text-grey min-[720px]:hidden">XCODE Web v0.9</p>
      </main>
      <p className="m-0 hidden px-12 pb-6 text-[13px] text-grey min-[720px]:block">Every sign in is recorded against your name. XCODE Web v0.9</p>
    </div>
  );
}

export function AuthHeading({ title, lead }: { title: ReactNode; lead: ReactNode }) {
  return (
    <div>
      <h1 id="auth-title" className="m-0 text-[28px] leading-[1.2] font-bold">
        {title}
      </h1>
      <p className="mt-1.5 mb-0 text-grey">{lead}</p>
    </div>
  );
}

export function AuthField({ label, htmlFor, action, children }: { label: string; htmlFor: string; action?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <label htmlFor={htmlFor} className="text-[15px] font-semibold">
          {label}
        </label>
        {action}
      </div>
      {children}
    </div>
  );
}

export function AuthInput({ digits = false, className, ...props }: ComponentProps<"input"> & { digits?: boolean }) {
  return (
    <input
      {...props}
      className={cn(
        "h-14 w-full rounded-xl border border-line bg-white px-4 text-[19px] focus:border-blue focus:outline-3 focus:outline-offset-1 focus:outline-blue/35 aria-invalid:border-2 aria-invalid:border-red min-[720px]:h-13",
        digits && "text-[22px] tracking-[0.4em] placeholder:text-[17px] placeholder:tracking-normal",
        className,
      )}
    />
  );
}

export function AuthFieldError({ id, children }: { id?: string; children: ReactNode }) {
  return (
    <p id={id} className="m-0 flex items-start gap-1.5 text-sm text-red">
      <AlertIcon className="mt-px shrink-0" />
      <span>{children}</span>
    </p>
  );
}

export function AuthButton({
  tone = "primary",
  className,
  type = "button",
  ...props
}: ComponentProps<"button"> & { tone?: "primary" | "outline" }) {
  return (
    <button
      {...props}
      type={type}
      className={cn(
        "inline-flex h-14 w-full items-center justify-center rounded-full text-[17px] font-semibold disabled:cursor-not-allowed disabled:opacity-55 min-[720px]:h-13",
        tone === "primary"
          ? "bg-blue text-white hover:enabled:bg-blue-dark aria-busy:cursor-progress aria-busy:bg-blue-busy"
          : "border-2 border-blue bg-transparent text-blue hover:enabled:bg-blue-tint",
        className,
      )}
    />
  );
}

export function CheckRow({ label, ...props }: Omit<ComponentProps<"input">, "type"> & { label: string }) {
  return (
    <label className="flex min-h-11 cursor-pointer items-start gap-3 pt-2.5 text-[15px]">
      <input {...props} type="checkbox" className="m-0 size-5.5 shrink-0 accent-blue" />
      <span>{label}</span>
    </label>
  );
}

// Dashed boxes for demo-only information: the one-time code (.demo) and the demo logins (.login-help).
export function DemoBox({ help = false, className, ...props }: ComponentProps<"div"> & { help?: boolean }) {
  return (
    <div {...props} className={cn("m-0 rounded-xl border border-dashed border-line px-3.5 text-sm text-grey", help ? "py-3" : "py-2.5", className)} />
  );
}
