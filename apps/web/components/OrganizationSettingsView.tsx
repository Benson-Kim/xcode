"use client";

import { useState, type ReactNode } from "react";
import { requestSetup } from "./requestSetup";
import { useSetupData } from "../lib/useSetupData";
import {
  Banner,
  Button,
  Card,
  CardHeader,
  Choice,
  ChoiceGroup,
  Field,
  FormActions,
  FormLayout,
  FormSkeleton,
  Grid2,
  PageHeader,
  SelectInput,
  TextInput,
  useToast,
} from "./ui";

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

type Section = keyof Pick<Settings, "organization" | "localization" | "branding" | "securityPolicy">;

// Change-log wording for each section.
const reasons: Record<Section, string> = {
  organization: "Updated organization details",
  localization: "Updated locale and time",
  branding: "Updated brand",
  securityPolicy: "Updated security policy",
};

const saved: Record<Section, string> = {
  organization: "Organization details saved.",
  localization: "Locale and time saved.",
  branding: "Brand saved.",
  securityPolicy: "Security policy saved.",
};

export function OrganizationSettingsView() {
  const loaded = useSetupData<Settings>("organization/settings");
  if (loaded.error)
    return (
      <section>
        <PageHeader title="Organization settings" />
        <Banner className="mt-5">{loaded.error}</Banner>
      </section>
    );
  if (loaded.loading || !loaded.data)
    return (
      <section>
        <PageHeader title="Organization settings" description="Defaults for everyone in the organization." />
        <FormSkeleton cards={4} label="Loading organization settings" />
      </section>
    );
  return <SettingsForm initial={loaded.data} />;
}

function SettingsForm({ initial }: { initial: Settings }) {
  const toast = useToast();
  const [settings, setSettings] = useState(initial);
  const [errors, setErrors] = useState<Partial<Record<Section, string>>>({});
  const [busy, setBusy] = useState<Section | null>(null);
  const update = <T extends Section>(section: T, value: Partial<Settings[T]>) => setSettings({ ...settings, [section]: { ...settings[section], ...value } });

  async function save(section: Section) {
    let value: object = settings[section];
    if (section === "organization") {
      const name = settings.organization.name.trim();
      const slug = settings.organization.slug.trim();
      if (!name || name.length > 200 || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) || slug.length > 100) {
        setErrors({ ...errors, organization: "Enter an organization name and a lowercase slug using letters, numbers, and hyphens." });
        return;
      }
      value = { name, slug };
    }
    setBusy(section);
    try {
      await requestSetup(`organization/settings/${section}`, { method: "PUT", body: JSON.stringify({ value, reason: reasons[section] }) });
      setErrors({ ...errors, [section]: undefined });
      toast(saved[section]);
    } catch (reason) {
      setErrors({ ...errors, [section]: (reason as Error).message });
    } finally {
      setBusy(null);
    }
  }

  const { organization, branding, localization, securityPolicy } = settings;
  return (
    <section>
      <PageHeader title="Organization settings" description="Defaults for everyone in the organization. Each person sets their own display under Your preferences." />
      <FormLayout>
        <SettingsCard title="Organization details" error={errors.organization} action="Save organization details" busy={busy === "organization"} onSave={() => void save("organization")}>
          <Grid2>
            <Field id="org-name" label="Organization name">
              <TextInput maxLength={200} value={organization.name} onChange={(event) => update("organization", { name: event.target.value })} />
            </Field>
            <Field id="org-slug" label="Slug" hint="Lowercase letters, numbers and hyphens.">
              <TextInput maxLength={100} value={organization.slug} onChange={(event) => update("organization", { slug: event.target.value })} />
            </Field>
          </Grid2>
        </SettingsCard>

        <SettingsCard title="Brand" error={errors.branding} action="Save brand" busy={busy === "branding"} onSave={() => void save("branding")}>
          <Grid2>
            <Field id="brand-display" label="Display name">
              <TextInput value={branding.displayName} onChange={(event) => update("branding", { displayName: event.target.value })} />
            </Field>
            <Field id="brand-legal" label="Legal name">
              <TextInput value={branding.legalName} onChange={(event) => update("branding", { legalName: event.target.value })} />
            </Field>
            <Field id="brand-alt" label="Logo alt text">
              <TextInput value={branding.logoAlt} onChange={(event) => update("branding", { logoAlt: event.target.value })} />
            </Field>
            <Field id="brand-email" label="Support email">
              <TextInput type="email" value={branding.supportEmail || ""} onChange={(event) => update("branding", { supportEmail: event.target.value || undefined })} />
            </Field>
            <Field id="brand-domain" label="Domain">
              <TextInput value={branding.domain || ""} onChange={(event) => update("branding", { domain: event.target.value || undefined })} />
            </Field>
          </Grid2>
        </SettingsCard>

        <SettingsCard title="Locale and time" error={errors.localization} action="Save locale" busy={busy === "localization"} onSave={() => void save("localization")}>
          <Grid2>
            <Field id="locale" label="Locale" hint="For example en-GB.">
              <TextInput value={localization.locale} onChange={(event) => update("localization", { locale: event.target.value })} />
            </Field>
            <Field id="time-zone" label="Time zone" hint="Business dates follow this zone, for example Africa/Nairobi.">
              <TextInput value={localization.timeZone} onChange={(event) => update("localization", { timeZone: event.target.value })} />
            </Field>
            <Field id="currency" label="Currency">
              <TextInput value={localization.currency} onChange={(event) => update("localization", { currency: event.target.value })} />
            </Field>
            <Field id="date-pattern" label="Date format">
              <SelectInput value={localization.datePattern} onChange={(event) => update("localization", { datePattern: event.target.value })}>
                <option value="short">Short</option>
                <option value="medium">Medium</option>
                <option value="long">Long</option>
              </SelectInput>
            </Field>
            <Field id="first-day" label="First day of week">
              <SelectInput value={localization.firstDayOfWeek} onChange={(event) => update("localization", { firstDayOfWeek: Number(event.target.value) })}>
                <option value="1">Monday</option>
                <option value="0">Sunday</option>
                <option value="6">Saturday</option>
              </SelectInput>
            </Field>
          </Grid2>
          <ChoiceGroup label="Time and overrides">
            <Choice label="Use 12-hour time" checked={localization.hour12} onChange={(event) => update("localization", { hour12: event.target.checked })} />
            <Choice label="Allow locale overrides" checked={localization.allowLocaleOverride} onChange={(event) => update("localization", { allowLocaleOverride: event.target.checked })} />
            <Choice
              label="Allow time-zone overrides"
              checked={localization.allowTimeZoneOverride}
              onChange={(event) => update("localization", { allowTimeZoneOverride: event.target.checked })}
            />
          </ChoiceGroup>
        </SettingsCard>

        <SettingsCard
          title="Security policy"
          description="Applied at sign-in for everyone in the organization."
          error={errors.securityPolicy}
          action="Save security"
          busy={busy === "securityPolicy"}
          onSave={() => void save("securityPolicy")}
        >
          <Grid2>
            <Field id="pin-length" label="Shortest new PIN" hint="4 to 8 digits. Existing PINs keep working.">
              <TextInput type="number" min="4" max="8" value={securityPolicy.pinLength} onChange={(event) => update("securityPolicy", { pinLength: Number(event.target.value) })} />
            </Field>
            <Field id="lockout-attempts" label="Wrong PINs before a pause" hint="1 to 10.">
              <TextInput
                type="number"
                min="1"
                max="10"
                value={securityPolicy.lockoutThreshold}
                onChange={(event) => update("securityPolicy", { lockoutThreshold: Number(event.target.value) })}
              />
            </Field>
            <Field id="lockout-minutes" label="Pause length in minutes">
              <TextInput type="number" min="1" max="1440" value={securityPolicy.lockoutMinutes} onChange={(event) => update("securityPolicy", { lockoutMinutes: Number(event.target.value) })} />
            </Field>
            <Field id="access-minutes" label="Session renews every (minutes)" hint="1 to 15.">
              <TextInput
                type="number"
                min="1"
                max="15"
                value={securityPolicy.accessTokenMinutes}
                onChange={(event) => update("securityPolicy", { accessTokenMinutes: Number(event.target.value) })}
              />
            </Field>
            <Field id="refresh-days" label="Stay signed in for (days)" hint="1 to 90.">
              <TextInput type="number" min="1" max="90" value={securityPolicy.refreshTokenDays} onChange={(event) => update("securityPolicy", { refreshTokenDays: Number(event.target.value) })} />
            </Field>
          </Grid2>
        </SettingsCard>
      </FormLayout>
    </section>
  );
}

function SettingsCard({
  title,
  description,
  error,
  action,
  busy,
  onSave,
  children,
}: {
  title: string;
  description?: string;
  error?: string;
  action: string;
  busy: boolean;
  onSave: () => void;
  children: ReactNode;
}) {
  return (
    <Card density="form" aria-label={title}>
      <CardHeader title={title} description={description} />
      {error && <Banner>{error}</Banner>}
      {children}
      <FormActions>
        <Button disabled={busy} onClick={onSave}>
          {action}
        </Button>
      </FormActions>
    </Card>
  );
}
