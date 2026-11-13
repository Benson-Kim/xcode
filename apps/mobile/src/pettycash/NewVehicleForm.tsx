import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { WEEKDAYS } from "@xcode/shared/dates";
import {
  normaliseRegistration,
  parseRevenueAmount,
} from "@xcode/shared/revenue";

import { SessionEndedError } from "../lib/api";
import { useFormats } from "../lib/formats";
import { Button, ErrorText, Field, Sheet, Text } from "../ui";
import { sendTo, useLoaded } from "./client";
import { Picker, SmallButton, type Option } from "./parts";

type Company = { id: string; name: string };

// A vehicle added from the expense, as its vehicle list names it, and the day it joins the fleet.
export type AddedVehicle = { option: Option; joinedOn: string };

type Errors = {
  registration?: string;
  fleetNumber?: string;
  company?: string;
  targets?: string;
};

// Monday first, the order the API reads dayTargets in.
const DAYS = [...WEEKDAYS.slice(1), WEEKDAYS[0]].map((day) => day.label);

const FLEET_NUMBER_LIMIT = 20;

// Each day's target, or null until every day has one above zero.
function dayTargets(texts: string[]): number[] | null {
  const figures: number[] = [];
  for (const text of texts) {
    const parsed = parseRevenueAmount(text);
    if (!parsed.ok || parsed.amount === null) return null;
    figures.push(parsed.amount);
  }
  return figures;
}

// The fleet's new vehicle, opened from the expense's vehicle list with what was typed there. An expense dated before
// the business date has the vehicle join on that date, so the expense can use it. Saving hands the vehicle back to
// the expense; cancelling, or a tap outside the sheet, goes back to it as it was.
export function NewVehicleForm({
  registration,
  date,
  businessDate,
  stamp,
  onSessionEnded,
  onCreated,
  onCancel,
}: {
  registration: string;
  date: string;
  businessDate: string;
  stamp: number;
  onSessionEnded: () => void;
  onCreated: (vehicle: AddedVehicle) => void;
  onCancel: () => void;
}) {
  const { formatDateOnly } = useFormats();
  const companies = useLoaded<Company[]>(
    "setup/vehicles/company-options",
    stamp,
    onSessionEnded,
  );
  const [form, setForm] = useState({
    registration: registration.toUpperCase(),
    fleetNumber: "",
    companyId: "",
    targets: DAYS.map(() => ""),
  });
  const [errors, setErrors] = useState<Errors>({});
  const [problem, setProblem] = useState("");
  const [saving, setSaving] = useState(false);
  const joinedOn = date < businessDate ? date : businessDate;
  const change = (next: Partial<typeof form>, field: keyof Errors) => {
    setForm({ ...form, ...next });
    setErrors({ ...errors, [field]: undefined });
  };

  async function save() {
    if (saving) return;
    const plate = normaliseRegistration(form.registration);
    const fleetNumber = form.fleetNumber.trim();
    const targets = dayTargets(form.targets);
    const found: Errors = {
      registration: plate ? undefined : "Enter the registration like KDN 204B.",
      fleetNumber: fleetNumber ? undefined : "Enter the fleet number.",
      company: form.companyId ? undefined : "Choose the PSV company.",
      targets: targets ? undefined : "Enter the target for every day.",
    };
    setErrors(found);
    setProblem("");
    if (!plate || !fleetNumber || !form.companyId || !targets) return;
    setSaving(true);
    try {
      const outcome = await sendTo<{ id: string }>("POST", "setup/vehicles", {
        registration: plate,
        companyId: form.companyId,
        joinedOn,
        fleetNumber,
        dayTargets: targets,
      });
      if (outcome.ok)
        onCreated({
          option: {
            value: outcome.data.id,
            label: plate,
            sub:
              companies.data?.find((company) => company.id === form.companyId)
                ?.name ?? "",
          },
          joinedOn,
        });
      else setProblem(outcome.message);
    } catch (reason) {
      if (reason instanceof SessionEndedError) onSessionEnded();
      else setProblem("The request could not be completed.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Sheet busy={saving} onClose={onCancel}>
      <Text weight="bold" style={{ fontSize: 17 }}>
        New vehicle
      </Text>
      {joinedOn < businessDate ? (
        <Text>{`Joins the fleet on ${formatDateOnly(joinedOn)}, the expense's date.`}</Text>
      ) : null}
      <Field
        label="Registration"
        value={form.registration}
        placeholder="KDN 204B"
        autoCapitalize="characters"
        autoCorrect={false}
        onChangeText={(text) =>
          change({ registration: text.toUpperCase() }, "registration")
        }
        error={errors.registration}
      />
      <Field
        label="Fleet number"
        value={form.fleetNumber}
        autoCorrect={false}
        maxLength={FLEET_NUMBER_LIMIT}
        onChangeText={(text) => change({ fleetNumber: text }, "fleetNumber")}
        error={errors.fleetNumber}
      />
      {companies.error ? <ErrorText>{companies.error}</ErrorText> : null}
      <Picker
        label="PSV company"
        options={(companies.data ?? []).map((company) => ({
          value: company.id,
          label: company.name,
        }))}
        value={form.companyId}
        onChange={(companyId) => change({ companyId }, "company")}
        error={errors.company}
        empty={companies.loading ? "Loading companies." : undefined}
      />
      <DayTargets
        values={form.targets}
        onChange={(targets) => change({ targets }, "targets")}
      />
      {errors.targets ? <ErrorText>{errors.targets}</ErrorText> : null}
      {problem ? <ErrorText>{problem}</ErrorText> : null}
      <View style={{ flexDirection: "row", gap: 12 }}>
        <Button tone="outline" disabled={saving} onPress={onCancel}>
          Cancel
        </Button>
        <Button onPress={() => void save()} disabled={saving}>
          Save vehicle
        </Button>
      </View>
    </Sheet>
  );
}

// A target for each day, Monday first. Same every day copies the first one typed to every day.
function DayTargets({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const first = values.find((text) => text.trim());
  return (
    <>
      <View style={styles.targetsHead}>
        <Text weight="semibold" style={{ flex: 1, fontSize: 15 }}>
          Target per day, KES
        </Text>
        <SmallButton
          disabled={!first}
          onPress={() => onChange(values.map(() => first ?? ""))}
        >
          Same every day
        </SmallButton>
      </View>
      <View style={styles.days}>
        {DAYS.map((day, index) => (
          <View key={day} style={styles.day}>
            <Field
              label={day}
              accessibilityLabel={`Target for ${day}`}
              value={values[index]}
              keyboardType="decimal-pad"
              autoCorrect={false}
              onChangeText={(text) =>
                onChange(
                  values.map((value, at) => (at === index ? text : value)),
                )
              }
            />
          </View>
        ))}
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  targetsHead: { flexDirection: "row", alignItems: "center", gap: 12 },
  days: { flexDirection: "row", flexWrap: "wrap", gap: 12 },
  day: { flexGrow: 1, flexBasis: "40%" },
});
