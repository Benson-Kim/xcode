"use client";

import { useState } from "react";

import type { SystemSetting, SystemSettings } from "@xcode/shared/appearance";

import { useAppearance } from "../lib/appearance";
import { useResource } from "../lib/data";
import {
  SYSTEM_SETTINGS_PATH,
  systemSettingsApi,
} from "../lib/endpoints/systemSettings";
import { useSession } from "../lib/session-context";
import { OrganizationSettingsView } from "./OrganizationSettingsView";
import {
  Banner,
  DataTable,
  PageHeader,
  RowAction,
  StatusBadge,
  Td,
  Tr,
  useToast,
} from "./ui";

// The Settings page (v2.38): the system settings for settings.edit, then the organization's own settings for
// organization.manage. Someone with only settings.edit sees the system settings alone.
export function SettingsScreen() {
  const { can } = useSession();
  const system = can("settings.edit") ? <SystemSettingsTable /> : null;
  if (can("organization.manage"))
    return <OrganizationSettingsView system={system} />;
  return (
    <>
      <PageHeader title="Settings" />
      {system}
    </>
  );
}

// One row a setting: its state and the switch. Switching acts at once for the whole system and is logged by the
// server; the appearance is read again so every screen follows it.
export function SystemSettingsTable() {
  const toast = useToast();
  const { refresh } = useAppearance();
  const loaded = useResource<SystemSettings>(SYSTEM_SETTINGS_PATH);
  const [latest, setLatest] = useState<SystemSettings | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  const rows = (latest ?? loaded.data)?.settings ?? [];

  async function flip(setting: SystemSetting) {
    const on = !setting.on;
    setBusy(setting.key);
    setError("");
    try {
      setLatest(await systemSettingsApi.switch(setting.key, on));
      refresh();
      toast(`${setting.label} switched ${on ? "on" : "off"}`);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      {(loaded.error || error) && <Banner>{error || loaded.error}</Banner>}
      <DataTable
        columns={[
          { label: "Setting" },
          { label: "State" },
          { label: "Actions", numeric: true },
        ]}
        loading={loaded.loading && !latest}
        loadingLabel="Loading settings"
        isEmpty={!rows.length}
        failed={Boolean(loaded.error)}
        emptyMessage="No system settings."
      >
        {rows.map((setting) => (
          <Tr key={setting.key}>
            <Td label="Setting" className="item">
              {setting.label}
            </Td>
            <Td label="State">
              <StatusBadge tone={setting.on ? "ok" : "neutral"}>
                {setting.on ? "On" : "Off"}
              </StatusBadge>
            </Td>
            <Td numeric>
              <div className="tacts">
                <RowAction
                  tone={setting.on ? "warn" : "ok"}
                  disabled={busy !== null}
                  aria-label={`${setting.on ? "Switch off" : "Switch on"} ${setting.label}`}
                  onClick={() => void flip(setting)}
                >
                  {setting.on ? "Switch off" : "Switch on"}
                </RowAction>
              </div>
            </Td>
          </Tr>
        ))}
      </DataTable>
    </>
  );
}
