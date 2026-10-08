"use client";

import { useState } from "react";

import { useAppearance } from "../lib/appearance";
import { apiRequest, useResource } from "../lib/data";
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

type Preferences = {
  locale?: string | null;
  timeZone?: string | null;
  hour12?: boolean | null;
  themeMode?: string | null;
  reducedMotion: boolean;
  fontScale: number;
  // Which overrides the organization allows (read-only; the API ignores them on save).
  allowLocaleOverride?: boolean;
  allowTimeZoneOverride?: boolean;
  allowHour12Override?: boolean;
  allowThemeOverride?: boolean;
  organization?: { locale: string; timeZone: string; hour12: boolean };
};

const LOCKED = "Your organization sets this for everyone.";

const description =
  "How XCODE looks for you. Organization defaults apply where you leave a field empty.";

// Personal display preferences: open to every active member, separate from organization administration.
export function PreferencesView() {
  const loaded = useResource<Preferences>("setup/preferences");
  if (loaded.error)
    return (
      <section>
        <PageHeader title="Your preferences" description={description} />
        <Banner className="mt-5">{loaded.error}</Banner>
      </section>
    );
  if (loaded.loading || !loaded.data)
    return (
      <section>
        <PageHeader title="Your preferences" description={description} />
        <FormSkeleton cards={1} fields={4} label="Loading your preferences" />
      </section>
    );
  return <PreferencesForm initial={loaded.data} />;
}

function PreferencesForm({ initial }: { initial: Preferences }) {
  const toast = useToast();
  const { refresh } = useAppearance();
  const [preferences, setPreferences] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  // An override the organization doesn't allow is shown as its value, but can't be changed here.
  const localeLocked = preferences.allowLocaleOverride === false;
  const zoneLocked = preferences.allowTimeZoneOverride === false;
  const hour12Locked = preferences.allowHour12Override === false;
  const themeLocked = preferences.allowThemeOverride === false;
  const organization = preferences.organization;
  const clockDefault = organization
    ? ` (${organization.hour12 ? "12-hour" : "24-hour"})`
    : "";
  async function save() {
    setBusy(true);
    try {
      await apiRequest("setup/preferences", {
        method: "PUT",
        body: JSON.stringify(preferences),
      });
      setError("");
      toast("Your preferences saved.");
      refresh();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <PageHeader title="Your preferences" description={description} />
      <FormLayout>
        {error && <Banner>{error}</Banner>}
        <Card density="form">
          <CardHeader title="Display" />
          <Grid2>
            <Field
              id="pref-locale"
              label="Locale override"
              hint={localeLocked ? LOCKED : undefined}
            >
              <TextInput
                value={
                  localeLocked
                    ? (organization?.locale ?? "")
                    : preferences.locale || ""
                }
                disabled={localeLocked}
                placeholder={
                  organization
                    ? `Organization default (${organization.locale})`
                    : "Use organization default"
                }
                onChange={(event) =>
                  setPreferences({
                    ...preferences,
                    locale: event.target.value || null,
                  })
                }
              />
            </Field>
            <Field
              id="pref-zone"
              label="Time-zone override"
              hint={zoneLocked ? LOCKED : undefined}
            >
              <TextInput
                value={
                  zoneLocked
                    ? (organization?.timeZone ?? "")
                    : preferences.timeZone || ""
                }
                disabled={zoneLocked}
                placeholder={
                  organization
                    ? `Organization default (${organization.timeZone})`
                    : "Use organization default"
                }
                onChange={(event) =>
                  setPreferences({
                    ...preferences,
                    timeZone: event.target.value || null,
                  })
                }
              />
            </Field>
            <Field
              id="pref-theme"
              label="Theme"
              hint={themeLocked ? LOCKED : undefined}
            >
              <SelectInput
                value={
                  themeLocked ? "light" : preferences.themeMode || "system"
                }
                disabled={themeLocked}
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
              </SelectInput>
            </Field>
            <Field
              id="pref-clock"
              label="Clock"
              hint={hour12Locked ? LOCKED : undefined}
            >
              <SelectInput
                value={
                  hour12Locked
                    ? "default"
                    : preferences.hour12 == null
                      ? "default"
                      : preferences.hour12
                        ? "12"
                        : "24"
                }
                disabled={hour12Locked}
                onChange={(event) =>
                  setPreferences({
                    ...preferences,
                    hour12:
                      event.target.value === "default"
                        ? null
                        : event.target.value === "12",
                  })
                }
              >
                <option value="default">
                  Organization default{clockDefault}
                </option>
                <option value="12">12-hour</option>
                <option value="24">24-hour</option>
              </SelectInput>
            </Field>
            <Field id="pref-font" label="Font scale" hint="1 to 3.">
              <TextInput
                type="number"
                min="1"
                max="3"
                step="0.1"
                value={preferences.fontScale}
                onChange={(event) =>
                  setPreferences({
                    ...preferences,
                    fontScale: Number(event.target.value),
                  })
                }
              />
            </Field>
          </Grid2>
          <ChoiceGroup label="Accessibility">
            <Choice
              label="Reduce motion"
              checked={preferences.reducedMotion}
              onChange={(event) =>
                setPreferences({
                  ...preferences,
                  reducedMotion: event.target.checked,
                })
              }
            />
          </ChoiceGroup>
          <FormActions>
            <Button tone="ok" disabled={busy} onClick={() => void save()}>
              Save preferences
            </Button>
          </FormActions>
        </Card>
      </FormLayout>
    </section>
  );
}
