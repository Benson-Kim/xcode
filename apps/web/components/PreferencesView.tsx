"use client";

import { useState } from "react";
import { requestSetup } from "./requestSetup";
import { useSetupData } from "../lib/useSetupData";
import { Banner, Button, Card, CardHeader, Choice, ChoiceGroup, Field, FormActions, FormLayout, FormSkeleton, Grid2, PageHeader, SelectInput, TextInput, useToast } from "./ui";

type Preferences = {
  locale?: string | null;
  timeZone?: string | null;
  hour12?: boolean | null;
  themeMode?: string | null;
  reducedMotion: boolean;
  fontScale: number;
};

const description = "How XCODE looks for you. Organization defaults apply where you leave a field empty.";

// Personal display preferences: open to every active member, separate from organization administration.
export function PreferencesView() {
  const loaded = useSetupData<Preferences>("preferences");
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
  const [preferences, setPreferences] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      await requestSetup("preferences", { method: "PUT", body: JSON.stringify(preferences) });
      setError("");
      toast("Your preferences saved.");
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
            <Field id="pref-locale" label="Locale override">
              <TextInput value={preferences.locale || ""} placeholder="Use organization default" onChange={(event) => setPreferences({ ...preferences, locale: event.target.value || null })} />
            </Field>
            <Field id="pref-zone" label="Time-zone override">
              <TextInput value={preferences.timeZone || ""} placeholder="Use organization default" onChange={(event) => setPreferences({ ...preferences, timeZone: event.target.value || null })} />
            </Field>
            <Field id="pref-theme" label="Theme">
              <SelectInput value={preferences.themeMode || "system"} onChange={(event) => setPreferences({ ...preferences, themeMode: event.target.value })}>
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </SelectInput>
            </Field>
            <Field id="pref-font" label="Font scale" hint="1 to 3.">
              <TextInput type="number" min="1" max="3" step="0.1" value={preferences.fontScale} onChange={(event) => setPreferences({ ...preferences, fontScale: Number(event.target.value) })} />
            </Field>
          </Grid2>
          <ChoiceGroup label="Accessibility">
            <Choice label="Reduce motion" checked={preferences.reducedMotion} onChange={(event) => setPreferences({ ...preferences, reducedMotion: event.target.checked })} />
            <Choice label="Use 12-hour time" checked={preferences.hour12 ?? false} onChange={(event) => setPreferences({ ...preferences, hour12: event.target.checked })} />
          </ChoiceGroup>
          <FormActions>
            <Button disabled={busy} onClick={() => void save()}>
              Save preferences
            </Button>
          </FormActions>
        </Card>
      </FormLayout>
    </section>
  );
}
