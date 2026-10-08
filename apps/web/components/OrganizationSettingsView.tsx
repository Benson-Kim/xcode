"use client";

import { useState, type ReactNode } from "react";

import { weekdayName } from "@xcode/shared/dates";

import { useAppearance } from "../lib/appearance";
import { useResource } from "../lib/data";
import { organizationApi } from "../lib/endpoints/organization";
import { useFormats } from "../lib/formats";
import {
  Banner,
  BrandIcon,
  Button,
  Card,
  CardHeader,
  Choice,
  ChoiceGroup,
  ColorInput,
  Field,
  FileButton,
  FormActions,
  FormLayout,
  FormSkeleton,
  Grid2,
  Hint,
  PageHeader,
  SelectInput,
  Skeleton,
  TextInput,
  useToast,
} from "./ui";

type Settings = {
  organization: { name: string; slug: string; businessDate?: string | null };
  effectiveBusinessDate?: string;
  // Today in the organization's time zone: the latest date the business date may be set to.
  calendarDate?: string;
  localization: {
    locale: string;
    timeZone: string;
    currency: string;
    datePattern: string;
    hour12: boolean;
    firstDayOfWeek: number;
    weekNumbering: string;
    useGrouping: boolean;
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

type Section = keyof Pick<
  Settings,
  "organization" | "localization" | "branding" | "securityPolicy"
>;

type PolicyNumber = Exclude<
  keyof Settings["securityPolicy"],
  "passwordComplexity" | "allowPinSignIn"
>;

// The security policy's bounds, as the server checks them (OrganizationSecurityPolicy.Validate). The form uses them
// for its inputs and hints, and checks every number before saving, including those it does not show.
const POLICY_BOUNDS: Record<
  PolicyNumber,
  { min: number; max: number; label: string }
> = {
  pinLength: { min: 4, max: 8, label: "Shortest new PIN" },
  lockoutThreshold: { min: 3, max: 10, label: "Wrong PINs before a pause" },
  lockoutMinutes: { min: 1, max: 60, label: "Pause length in minutes" },
  accessTokenMinutes: {
    min: 1,
    max: 15,
    label: "Session renews every (minutes)",
  },
  refreshTokenDays: { min: 1, max: 90, label: "Stay signed in for (days)" },
  idleUnlockSeconds: { min: 30, max: 3600, label: "Idle unlock (seconds)" },
  passwordMinLength: { min: 12, max: 128, label: "Shortest password" },
  passwordHistory: { min: 0, max: 24, label: "Passwords remembered" },
};

// Every number outside its bounds, field by field, rather than the server's one-line refusal. Empty when all are in.
function policyProblem(policy: Settings["securityPolicy"]) {
  return (
    Object.entries(POLICY_BOUNDS) as [
      PolicyNumber,
      (typeof POLICY_BOUNDS)[PolicyNumber],
    ][]
  )
    .filter(
      ([key, { min, max }]) =>
        !Number.isInteger(policy[key]) ||
        policy[key] < min ||
        policy[key] > max,
    )
    .map(
      ([, { min, max, label }]) =>
        `${label} must be a whole number from ${min} to ${max}.`,
    )
    .join(" ");
}

const bounds = (key: PolicyNumber) => ({
  min: String(POLICY_BOUNDS[key].min),
  max: String(POLICY_BOUNDS[key].max),
});

// The toast after each save. Saves carry no typed reason: the server writes one for the change log.
const saved: Record<Section, string> = {
  organization: "Organization details saved.",
  localization: "Locale and time saved.",
  branding: "Brand saved.",
  securityPolicy: "Security policy saved.",
};

export function OrganizationSettingsView() {
  const loaded = useResource<Settings>("setup/organization/settings");
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
        <PageHeader
          title="Organization settings"
          description="Defaults for everyone in the organization."
        />
        <FormSkeleton cards={5} label="Loading organization settings" />
      </section>
    );
  // Reloaded after every save: the calendar date and the effective business date are worked out by the server.
  return <SettingsForm initial={loaded.data} onSaved={loaded.reload} />;
}

const LOGO_TYPES = ["image/png", "image/jpeg", "image/webp"];
const LOGO_MAX_BYTES = 256 * 1024;

function readAsDataUrl(file: File) {
  return new Promise<string>((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("The image could not be read."));
    reader.readAsDataURL(file);
  });
}

function SettingsForm({
  initial,
  onSaved,
}: {
  initial: Settings;
  onSaved: () => void;
}) {
  const toast = useToast();
  const { formatDateOnly } = useFormats();
  // Saved settings show at once: the shell reloads branding and formats after each save.
  const { appearance, loading: appearanceLoading, refresh } = useAppearance();
  const [logoBusy, setLogoBusy] = useState(false);
  const [settings, setSettings] = useState(initial);
  const [errors, setErrors] = useState<Partial<Record<Section, string>>>({});
  const [businessDateError, setBusinessDateError] = useState("");
  const [busy, setBusy] = useState<Section | null>(null);
  const [businessDateBusy, setBusinessDateBusy] = useState(false);
  const update = <T extends Section>(section: T, value: Partial<Settings[T]>) =>
    setSettings({ ...settings, [section]: { ...settings[section], ...value } });

  async function save(section: Section) {
    let value: object = settings[section];
    if (section === "securityPolicy") {
      // Said here, field by field, rather than as the server's one-line refusal. The pause is capped at one hour.
      const policy = settings.securityPolicy;
      const limits: [string, number, number, number][] = [
        ["Shortest new PIN", policy.pinLength, 4, 8],
        ["Wrong PINs before a pause", policy.lockoutThreshold, 3, 10],
        ["Pause length", policy.lockoutMinutes, 1, 60],
        ["Session renews every", policy.accessTokenMinutes, 1, 15],
        ["Stay signed in for", policy.refreshTokenDays, 1, 90],
      ];
      const outside = limits.filter(
        ([, current, min, max]) =>
          !Number.isInteger(current) || current < min || current > max,
      );
      if (outside.length) {
        setErrors({
          ...errors,
          securityPolicy: outside
            .map(([label, , min, max]) => `${label}: use ${min} to ${max}.`)
            .join(" "),
        });
        return;
      }
    }
    if (section === "organization") {
      const name = settings.organization.name.trim();
      const slug = settings.organization.slug.trim();
      if (
        !name ||
        name.length > 200 ||
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(slug) ||
        slug.length > 100
      ) {
        setErrors({
          ...errors,
          organization:
            "Enter an organization name and a lowercase slug using letters, numbers, and hyphens.",
        });
        return;
      }
      value = { name, slug };
    }
    if (section === "securityPolicy") {
      const problem = policyProblem(settings.securityPolicy);
      if (problem) return setErrors({ ...errors, securityPolicy: problem });
    }
    setBusy(section);
    try {
      await organizationApi.saveSection(section, value);
      setErrors({ ...errors, [section]: undefined });
      toast(saved[section]);
      refresh();
      onSaved();
    } catch (reason) {
      setErrors({ ...errors, [section]: (reason as Error).message });
    } finally {
      setBusy(null);
    }
  }

  async function saveBusinessDate() {
    const value = settings.organization.businessDate || null;
    setBusinessDateBusy(true);
    try {
      await organizationApi.saveBusinessDate(value);
      setBusinessDateError("");
      toast(
        value
          ? "Business date saved."
          : "Business date now follows the organization time zone.",
      );
      refresh();
      onSaved();
    } catch (reason) {
      setBusinessDateError((reason as Error).message);
    } finally {
      setBusinessDateBusy(false);
    }
  }

  async function changeLogo(file: File | null) {
    if (file && !LOGO_TYPES.includes(file.type))
      return setErrors({
        ...errors,
        branding: "Upload a PNG, JPEG or WebP image.",
      });
    if (file && file.size > LOGO_MAX_BYTES)
      return setErrors({
        ...errors,
        branding: "The logo must be at most 256 KB.",
      });
    setLogoBusy(true);
    try {
      if (file) await organizationApi.uploadLogo(await readAsDataUrl(file));
      else await organizationApi.removeLogo();
      setErrors({ ...errors, branding: undefined });
      toast(file ? "Logo updated." : "Logo removed.");
      refresh();
      onSaved();
    } catch (reason) {
      setErrors({ ...errors, branding: (reason as Error).message });
    } finally {
      setLogoBusy(false);
    }
  }

  const { organization, branding, localization, securityPolicy } = settings;
  // The business date the form will save: a held date, or null to follow the organization's calendar date. The field
  // and its hint follow it, so dropping a held date shows the calendar date at once, before it is saved. The calendar
  // date itself is read again after every save.
  const held = organization.businessDate || null;
  const logo = appearance?.branding.logo;
  return (
    <section>
      <PageHeader
        title="Organization settings"
        description="Defaults for everyone in the organization. Each person sets their own display under Your preferences."
      />
      <FormLayout>
        <SettingsCard
          title="Organization details"
          error={errors.organization}
          action="Save organization details"
          busy={busy === "organization"}
          onSave={() => void save("organization")}
        >
          <Grid2>
            <Field id="org-name" label="Organization name">
              <TextInput
                maxLength={200}
                value={organization.name}
                onChange={(event) =>
                  update("organization", { name: event.target.value })
                }
              />
            </Field>
            <Field
              id="org-slug"
              label="Slug"
              hint="Lowercase letters, numbers and hyphens."
            >
              <TextInput
                maxLength={100}
                value={organization.slug}
                onChange={(event) =>
                  update("organization", { slug: event.target.value })
                }
              />
            </Field>
          </Grid2>
        </SettingsCard>

        <SettingsCard
          title="Business date"
          description="The accounting date used by reports, targets, scheduled postings, and setup changes. Leave it blank to follow the organization's time zone."
          error={businessDateError}
          action="Save business date"
          busy={businessDateBusy}
          onSave={() => void saveBusinessDate()}
        >
          <Grid2 narrow>
            <Field
              id="business-date"
              label="Business date"
              hint={
                held
                  ? `Held at ${formatDateOnly(held)}.${initial.calendarDate ? ` The organization's calendar date is ${formatDateOnly(initial.calendarDate)}.` : ""}`
                  : initial.calendarDate
                    ? `Following the organization's calendar date, ${formatDateOnly(initial.calendarDate)}.`
                    : "Following the organization's calendar date."
              }
            >
              <TextInput
                type="date"
                // Without a held date the business date is the organization's calendar date.
                value={
                  held ||
                  initial.calendarDate ||
                  initial.effectiveBusinessDate ||
                  ""
                }
                max={initial.calendarDate}
                onChange={(event) =>
                  setSettings({
                    ...settings,
                    organization: {
                      ...organization,
                      businessDate: event.target.value || null,
                    },
                  })
                }
              />
            </Field>
          </Grid2>
          {held && (
            <Button
              tone="outline"
              disabled={businessDateBusy}
              onClick={() =>
                setSettings({
                  ...settings,
                  organization: { ...organization, businessDate: null },
                })
              }
            >
              Follow organization time zone
            </Button>
          )}
        </SettingsCard>

        <SettingsCard
          title="Brand"
          description="Shown to everyone as soon as you save."
          error={errors.branding}
          action="Save brand"
          busy={busy === "branding"}
          onSave={() => void save("branding")}
        >
          <div className="flex flex-wrap items-center gap-4">
            <span className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-[14px] border border-card-line bg-paper">
              {appearanceLoading ? (
                <Skeleton className="size-10 rounded-[10px]" />
              ) : logo ? (
                // The logo is a data URL from the API, which next/image cannot optimise.

                <img
                  src={logo}
                  alt={branding.logoAlt}
                  className="size-full object-contain p-1.5"
                />
              ) : (
                <span
                  aria-hidden="true"
                  className="grid size-10 place-items-center rounded-[10px] bg-brand text-white"
                >
                  <BrandIcon />
                </span>
              )}
            </span>
            <div className="flex min-w-0 flex-col gap-1.5">
              <div className="flex flex-wrap gap-2">
                <FileButton
                  accept={LOGO_TYPES.join(",")}
                  disabled={logoBusy}
                  onFile={(file) => void changeLogo(file)}
                >
                  {logo ? "Replace logo" : "Upload logo"}
                </FileButton>
                {logo && (
                  <Button
                    tone="danger"
                    disabled={logoBusy}
                    onClick={() => void changeLogo(null)}
                  >
                    Remove logo
                  </Button>
                )}
              </div>
              <Hint>
                PNG, JPEG or WebP, up to 256 KB. A square image works best.
              </Hint>
            </div>
          </div>
          <Grid2>
            <Field id="brand-display" label="Display name">
              <TextInput
                value={branding.displayName}
                onChange={(event) =>
                  update("branding", { displayName: event.target.value })
                }
              />
            </Field>
            <Field id="brand-legal" label="Legal name">
              <TextInput
                value={branding.legalName}
                onChange={(event) =>
                  update("branding", { legalName: event.target.value })
                }
              />
            </Field>
            <Field id="brand-alt" label="Logo alt text">
              <TextInput
                value={branding.logoAlt}
                onChange={(event) =>
                  update("branding", { logoAlt: event.target.value })
                }
              />
            </Field>
            <Field id="brand-email" label="Support email">
              <TextInput
                type="email"
                value={branding.supportEmail || ""}
                onChange={(event) =>
                  update("branding", {
                    supportEmail: event.target.value || undefined,
                  })
                }
              />
            </Field>
            <Field id="brand-domain" label="Domain">
              <TextInput
                value={branding.domain || ""}
                onChange={(event) =>
                  update("branding", {
                    domain: event.target.value || undefined,
                  })
                }
              />
            </Field>
          </Grid2>
          <Grid2>
            <Field
              id="brand-primary"
              label="Primary colour"
              hint="Buttons, links and the selected menu entry."
            >
              <ColorInput
                pickerLabel="Pick the primary colour"
                value={branding.primary}
                onChange={(primary) => update("branding", { primary })}
              />
            </Field>
            <Field
              id="brand-secondary"
              label="Secondary colour"
              hint="The brand mark and avatar."
            >
              <ColorInput
                pickerLabel="Pick the secondary colour"
                value={branding.secondary}
                onChange={(secondary) => update("branding", { secondary })}
              />
            </Field>
            <Field
              id="brand-accent"
              label="Accent colour"
              hint="Positive states, such as Active and Balanced."
            >
              <ColorInput
                pickerLabel="Pick the accent colour"
                value={branding.accent}
                onChange={(accent) => update("branding", { accent })}
              />
            </Field>
          </Grid2>
          <Hint>
            Colours must stay readable on white: at least 4.5 to 1 contrast.
          </Hint>
        </SettingsCard>

        <SettingsCard
          title="Locale and time"
          error={errors.localization}
          action="Save locale"
          busy={busy === "localization"}
          onSave={() => void save("localization")}
        >
          <Grid2>
            <Field id="locale" label="Locale" hint="For example en-GB.">
              <TextInput
                value={localization.locale}
                onChange={(event) =>
                  update("localization", { locale: event.target.value })
                }
              />
            </Field>
            <Field
              id="time-zone"
              label="Time zone"
              hint="Business dates follow this zone, for example Africa/Nairobi."
            >
              <TextInput
                value={localization.timeZone}
                onChange={(event) =>
                  update("localization", { timeZone: event.target.value })
                }
              />
            </Field>
            <Field id="currency" label="Currency">
              <TextInput
                value={localization.currency}
                onChange={(event) =>
                  update("localization", { currency: event.target.value })
                }
              />
            </Field>
            <Field id="date-pattern" label="Date format">
              <SelectInput
                value={localization.datePattern}
                onChange={(event) =>
                  update("localization", { datePattern: event.target.value })
                }
              >
                <option value="short">Short</option>
                <option value="medium">Medium</option>
                <option value="long">Long</option>
              </SelectInput>
            </Field>
            <Field id="first-day" label="First day of week">
              <SelectInput
                value={localization.firstDayOfWeek}
                onChange={(event) =>
                  update("localization", {
                    firstDayOfWeek: Number(event.target.value),
                  })
                }
              >
                <option value="1">{weekdayName(1)}</option>
                <option value="0">{weekdayName(0)}</option>
                <option value="6">{weekdayName(6)}</option>
                {/* The API takes any day; one set elsewhere is shown as it is rather than as Monday. */}
                {![0, 1, 6].includes(localization.firstDayOfWeek) && (
                  <option value={localization.firstDayOfWeek}>
                    {weekdayName(localization.firstDayOfWeek) ??
                      localization.firstDayOfWeek}
                  </option>
                )}
              </SelectInput>
            </Field>
          </Grid2>
          <ChoiceGroup label="Time and overrides">
            <Choice
              label="Use 12-hour time"
              checked={localization.hour12}
              onChange={(event) =>
                update("localization", { hour12: event.target.checked })
              }
            />
            <Choice
              label="Allow locale overrides"
              checked={localization.allowLocaleOverride}
              onChange={(event) =>
                update("localization", {
                  allowLocaleOverride: event.target.checked,
                })
              }
            />
            <Choice
              label="Allow time-zone overrides"
              checked={localization.allowTimeZoneOverride}
              onChange={(event) =>
                update("localization", {
                  allowTimeZoneOverride: event.target.checked,
                })
              }
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
            <Field
              id="pin-length"
              label="Shortest new PIN"
              hint="4 to 8 digits. Existing PINs keep working."
            >
              <TextInput
                type="number"
                {...bounds("pinLength")}
                value={securityPolicy.pinLength}
                onChange={(event) =>
                  update("securityPolicy", {
                    pinLength: Number(event.target.value),
                  })
                }
              />
            </Field>
            <Field
              id="lockout-attempts"
              label="Wrong PINs before a pause"
              hint="3 to 10."
            >
              <TextInput
                type="number"
                {...bounds("lockoutThreshold")}
                value={securityPolicy.lockoutThreshold}
                onChange={(event) =>
                  update("securityPolicy", {
                    lockoutThreshold: Number(event.target.value),
                  })
                }
              />
            </Field>
            <Field
              id="lockout-minutes"
              label="Pause length in minutes"
              hint="1 to 60, so a pause lasts at most an hour. A PIN reset by email still lifts a pause."
            >
              <TextInput
                type="number"
                {...bounds("lockoutMinutes")}
                value={securityPolicy.lockoutMinutes}
                onChange={(event) =>
                  update("securityPolicy", {
                    lockoutMinutes: Number(event.target.value),
                  })
                }
              />
            </Field>
            <Field
              id="access-minutes"
              label="Session renews every (minutes)"
              hint="1 to 15."
            >
              <TextInput
                type="number"
                {...bounds("accessTokenMinutes")}
                value={securityPolicy.accessTokenMinutes}
                onChange={(event) =>
                  update("securityPolicy", {
                    accessTokenMinutes: Number(event.target.value),
                  })
                }
              />
            </Field>
            <Field
              id="refresh-days"
              label="Stay signed in for (days)"
              hint="1 to 90."
            >
              <TextInput
                type="number"
                {...bounds("refreshTokenDays")}
                value={securityPolicy.refreshTokenDays}
                onChange={(event) =>
                  update("securityPolicy", {
                    refreshTokenDays: Number(event.target.value),
                  })
                }
              />
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
        <Button tone="ok" disabled={busy} onClick={onSave}>
          {action}
        </Button>
      </FormActions>
    </Card>
  );
}
