import { useState } from "react";
import { StyleSheet, View } from "react-native";

import { mondayFirstIndex, weekdaysFrom } from "@xcode/shared/dates";
import {
  DEFAULT_LOW_BELOW,
  normaliseRegistration,
  parseRevenueAmount,
} from "@xcode/shared/revenue";

import { SessionEndedError } from "../lib/api";
import { useFormats } from "../lib/formats";
import { useTargets } from "../shell/targets";
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
  lowBelow?: string;
};

// The day targets are kept Monday first, the order the API reads dayTargets in.
const DAY_COUNT = 7;

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

const NO_TARGETS = Array<number>(DAY_COUNT).fill(0);

const lowFigure = (text: string) => (text === "" ? null : Number(text));

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
  const targetsShown = useTargets();
  const companies = useLoaded<Company[]>(
    "setup/vehicles/company-options",
    stamp,
    onSessionEnded,
  );
  const [form, setForm] = useState({
    registration: registration.toUpperCase(),
    fleetNumber: "",
    companyId: "",
    targets: Array<string>(DAY_COUNT).fill(""),
    lowBelow: String(DEFAULT_LOW_BELOW),
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
    // With Targets switched off no day targets are asked, and the vehicle is saved with none.
    const targets = targetsShown ? dayTargets(form.targets) : NO_TARGETS;
    const lowBelow = lowFigure(form.lowBelow);
    const found: Errors = {
      registration: plate ? undefined : "Enter the registration like KDN 204B.",
      fleetNumber: fleetNumber ? undefined : "Enter the fleet number.",
      company: form.companyId ? undefined : "Choose the PSV company.",
      targets: targets ? undefined : "Enter the target for every day.",
      lowBelow: lowBelow === null ? "Enter the low revenue figure." : undefined,
    };
    setErrors(found);
    setProblem("");
    if (
      !plate ||
      !fleetNumber ||
      !form.companyId ||
      !targets ||
      lowBelow === null
    )
      return;
    setSaving(true);
    try {
      const outcome = await sendTo<{ id: string }>("POST", "setup/vehicles", {
        registration: plate,
        companyId: form.companyId,
        joinedOn,
        fleetNumber,
        dayTargets: targets,
        lowBelow,
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
      {targetsShown ? (
        <>
          <DayTargets
            values={form.targets}
            onChange={(targets) => change({ targets }, "targets")}
          />
          {errors.targets ? <ErrorText>{errors.targets}</ErrorText> : null}
        </>
      ) : null}
      <Field
        label="Low revenue below, KES"
        value={form.lowBelow}
        keyboardType="number-pad"
        autoCorrect={false}
        onChangeText={(text) =>
          change({ lowBelow: text.replace(/\D/g, "") }, "lowBelow")
        }
        error={errors.lowBelow}
      />
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

// A target for each day, shown from the first day of the week (Sunday, v2.41). Same every day copies the first one
// typed, from Sunday onwards, to every day.
function DayTargets({
  values,
  onChange,
}: {
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const { firstDayOfWeek } = useFormats();
  const shown = weekdaysFrom(firstDayOfWeek()).map((day) => ({
    name: day.label,
    at: mondayFirstIndex(day.value),
  }));
  const first = shown
    .map(({ at }) => values[at] ?? "")
    .find((text) => text.trim());
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
        {shown.map(({ name: day, at: index }) => (
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
