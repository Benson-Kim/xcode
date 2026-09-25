"use client";

import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { requestSetup } from "./requestSetup";

type Settings = {
  organization: { name: string; slug: string };
  localization: {
    locale: string;
    timeZone: string;
    currency: string;
    datePattern: string;
    hour12: boolean;
    firstDayOfWeek: number;
    weekNumbering: string;
    useGroupping: boolean;
    numberDecimals: number;
    allowLocaleOverride: boolean;
    allowTimeZoneOverride: boolean;
    allowHour12Override: boolean;
    allowThemeOverride: boolean;
  };
  branding: {
    displayName: string;
    legalName: string;
    logoAlt: string;
    supportEmail?: string;
    domain?: string;
    primary: string;
    secondary: string;
    accent: string;
  };
  securityPolicy: {
    passwordMinLength: number;
    passwordComplexity: boolean;
    passwordHistory: number;
    pinLength: number;
    lockoutThreshold: number;
    lockoutMinutes: number;
    accessTokenMinutes: number;
    refreshTokenDays: number;
    idleUnlockSeconds: number;
    allowPinSignIn: boolean;
  };
};
type Preferences = {
  locale?: string;
  timeZone?: string;
  hour12?: boolean;
  themeMode?: string;
  reducedMotion: boolean;
  fontScale: number;
};

const updateSection = <T extends keyof Settings>(
  settings: Settings,
  section: T,
  value: Partial<Settings[T]>,
) => ({ ...settings, [section]: { ...settings[section], ...value } });

export function OrganizationSettingsView() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [preferences, setPreferences] = useState<Preferences>({
    reducedMotion: false,
    fontScale: 1,
  });
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  useEffect(() => {
    Promise.all([
      requestSetup<Settings>("organization/settings"),
      requestSetup<Preferences>("preferences"),
    ])
      .then(([nextSettings, nextPreferences]) => {
        setSettings(nextSettings);
        setPreferences(nextPreferences);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);
  async function save(
    section: "localization" | "branding" | "securityPolicy",
    value: object,
  ) {
    try {
      await requestSetup(`organization/settings/${section}`, {
        method: "PUT",
        body: JSON.stringify({
          value,
          reason: "Updated organization settings",
        }),
      });
      setSaved("Organization settings saved.");
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  async function savePreferences() {
    try {
      await requestSetup("preferences", {
        method: "PUT",
        body: JSON.stringify(preferences),
      });
      setSaved("Your preferences saved.");
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  if (!settings)
    return (
      <section>
        <p className="eyebrow">Organization</p>
        <h1>Settings</h1>
        {error ? (
          <p className="error-box" role="alert">
            {error}
          </p>
        ) : (
          <p className="muted">Loading settings...</p>
        )}
      </section>
    );
  return (
    <section>
      <div className="page-head">
        <div>
          <p className="eyebrow">Organization</p>
          <h1>Settings</h1>
          <p className="muted">
            Keep the organization defaults and your personal display preferences
            in one place.
          </p>
        </div>
      </div>
      {error && (
        <p className="error-box" role="alert">
          {error}
        </p>
      )}
      {saved && (
        <p className="success-box" role="status">
          {saved}
        </p>
      )}
      <div className="settings-grid">
        <SettingsSection title="Organization details">
          <label>
            Organization name
            <input value={settings.organization.name} readOnly />
          </label>
          <label>
            Slug
            <input value={settings.organization.slug} readOnly />
          </label>
        </SettingsSection>
        <SettingsSection title="Locale and time">
          <label>
            Locale
            <input
              value={settings.localization.locale}
              onChange={(event) =>
                setSettings(updateSection(settings, "localization", { locale: event.target.value }))
              }
            />
          </label>
          <label>
            Time zone
            <input
              value={settings.localization.timeZone}
              onChange={(event) =>
                setSettings(updateSection(settings, "localization", { timeZone: event.target.value }))
              }
            />
          </label>
          <label>
            Currency
            <input
              value={settings.localization.currency}
              onChange={(event) =>
                setSettings(updateSection(settings, "localization", { currency: event.target.value }))
              }
            />
          </label>
          <label>
            Date format
            <select value={settings.localization.datePattern} onChange={(event) => setSettings(updateSection(settings, "localization", { datePattern: event.target.value }))}>
              <option value="short">Short</option><option value="medium">Medium</option><option value="long">Long</option>
            </select>
          </label>
          <label>
            First day of week
            <select value={settings.localization.firstDayOfWeek} onChange={(event) => setSettings(updateSection(settings, "localization", { firstDayOfWeek: Number(event.target.value) }))}>
              <option value="0">Sunday</option><option value="1">Monday</option><option value="6">Saturday</option>
            </select>
          </label>
          <label className="check"><input type="checkbox" checked={settings.localization.hour12} onChange={(event) => setSettings(updateSection(settings, "localization", { hour12: event.target.checked }))} /> Use 12-hour time</label>
          <label className="check"><input type="checkbox" checked={settings.localization.allowLocaleOverride} onChange={(event) => setSettings(updateSection(settings, "localization", { allowLocaleOverride: event.target.checked }))} /> Allow locale overrides</label>
          <label className="check"><input type="checkbox" checked={settings.localization.allowTimeZoneOverride} onChange={(event) => setSettings(updateSection(settings, "localization", { allowTimeZoneOverride: event.target.checked }))} /> Allow time-zone overrides</label>
          <button
            className="btn-pill"
            onClick={() => void save("localization", settings.localization)}
          >
            Save locale
          </button>
        </SettingsSection>
        <SettingsSection title="Brand">
          <label>
            Display name
            <input
              value={settings.branding.displayName}
              onChange={(event) =>
                setSettings(updateSection(settings, "branding", { displayName: event.target.value }))
              }
            />
          </label>
          <label>
            Legal name
            <input
              value={settings.branding.legalName}
              onChange={(event) =>
                setSettings(updateSection(settings, "branding", { legalName: event.target.value }))
              }
            />
          </label>
          <label>
            Logo alt text
            <input value={settings.branding.logoAlt} onChange={(event) => setSettings(updateSection(settings, "branding", { logoAlt: event.target.value }))} />
          </label>
          <label>
            Support email
            <input type="email" value={settings.branding.supportEmail || ""} onChange={(event) => setSettings(updateSection(settings, "branding", { supportEmail: event.target.value || undefined }))} />
          </label>
          <label>
            Domain
            <input value={settings.branding.domain || ""} onChange={(event) => setSettings(updateSection(settings, "branding", { domain: event.target.value || undefined }))} />
          </label>
          <button
            className="btn-pill"
            onClick={() => void save("branding", settings.branding)}
          >
            Save brand
          </button>
        </SettingsSection>
        <SettingsSection title="Security policy">
          <label>
            PIN length
            <input
              type="number"
              min="4"
              max="8"
              value={settings.securityPolicy.pinLength}
              onChange={(event) =>
                setSettings(updateSection(settings, "securityPolicy", { pinLength: Number(event.target.value) }))
              }
            />
          </label>
          <label>
            Lockout attempts
            <input
              type="number"
              min="1"
              max="10"
              value={settings.securityPolicy.lockoutThreshold}
              onChange={(event) =>
                setSettings(updateSection(settings, "securityPolicy", { lockoutThreshold: Number(event.target.value) }))
              }
            />
          </label>
          <label>
            Lockout minutes
            <input type="number" min="1" max="1440" value={settings.securityPolicy.lockoutMinutes} onChange={(event) => setSettings(updateSection(settings, "securityPolicy", { lockoutMinutes: Number(event.target.value) }))} />
          </label>
          <label>
            Minimum password length
            <input type="number" min="12" max="128" value={settings.securityPolicy.passwordMinLength} onChange={(event) => setSettings(updateSection(settings, "securityPolicy", { passwordMinLength: Number(event.target.value) }))} />
          </label>
          <label>
            Refresh token days
            <input type="number" min="1" max="90" value={settings.securityPolicy.refreshTokenDays} onChange={(event) => setSettings(updateSection(settings, "securityPolicy", { refreshTokenDays: Number(event.target.value) }))} />
          </label>
          <label className="check"><input type="checkbox" checked={settings.securityPolicy.passwordComplexity} onChange={(event) => setSettings(updateSection(settings, "securityPolicy", { passwordComplexity: event.target.checked }))} /> Require password complexity</label>
          <label className="check">
            <input
              type="checkbox"
              checked={settings.securityPolicy.allowPinSignIn}
              onChange={(event) =>
                setSettings(updateSection(settings, "securityPolicy", { allowPinSignIn: event.target.checked }))
              }
            />
            Allow PIN sign-in
          </label>
          <button
            className="btn-pill"
            onClick={() => void save("securityPolicy", settings.securityPolicy)}
          >
            Save security
          </button>
        </SettingsSection>
        <SettingsSection title="Your preferences">
          <label>
            Locale override
            <input value={preferences.locale || ""} placeholder="Use organization default" onChange={(event) => setPreferences({ ...preferences, locale: event.target.value || undefined })} />
          </label>
          <label>
            Time-zone override
            <input value={preferences.timeZone || ""} placeholder="Use organization default" onChange={(event) => setPreferences({ ...preferences, timeZone: event.target.value || undefined })} />
          </label>
          <label>
            Theme
            <select
              value={preferences.themeMode || "system"}
              onChange={(event) =>
                setPreferences({
                  ...preferences,
                  themeMode: event.target.value,
                })
              }
            >
              <option value="system">System</option>
              <option value="light">Light</option>
              <option value="dark">Dark</option>
            </select>
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={preferences.reducedMotion}
              onChange={(event) =>
                setPreferences({
                  ...preferences,
                  reducedMotion: event.target.checked,
                })
              }
            />{" "}
            Reduce motion
          </label>
          <label className="check"><input type="checkbox" checked={preferences.hour12 ?? false} onChange={(event) => setPreferences({ ...preferences, hour12: event.target.checked })} /> Use 12-hour time</label>
          <label>
            Font scale
            <input
              type="number"
              min="1"
              max="3"
              step="0.1"
              value={preferences.fontScale}
              onChange={(event) =>
                setPreferences({ ...preferences, fontScale: Number(event.target.value) })
              }
            />
          </label>
          <button className="btn-pill" onClick={() => void savePreferences()}>
            Save preferences
          </button>
        </SettingsSection>
      </div>
    </section>
  );
}

function SettingsSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <article className="card settings-section">
      <h2 className="card-title">{title}</h2>
      {children}
    </article>
  );
}
