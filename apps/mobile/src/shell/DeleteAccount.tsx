import { useRef, useState } from "react";
import { StyleSheet, View } from "react-native";

import { wrongPinMessage } from "../auth/attempts";
import { failureMessage, isRefused } from "../auth/authErrors";
import { useAlive, useDelayedSubmit, useOperationLock } from "../auth/hooks";
import { LinkRow, PinPad } from "../auth/PinPad";
import {
  SessionEndedError,
  apiSendResult,
  authApi,
  keepSession,
} from "../lib/api";
import type { StoredPerson } from "../lib/storage";
import { Button, LinkButton, Text, useTheme } from "../ui";

const NO_INTERNET = "No internet. Asking to delete your account needs network.";

// The server checks the PIN and counts wrong tries on every device. The phone's own check would let someone holding
// an unlocked phone guess the PIN without limit.
async function confirmPin(person: StoredPerson, pin: string) {
  const result = await authApi("pin", { phoneNumber: person.phoneNumber, pin });
  if (result.status !== "authenticated") return false;
  await keepSession(person.phoneNumber, result);
  return true;
}

function messageFor(failure: unknown) {
  if (isRefused(failure) && typeof failure.response.triesLeft === "number")
    return wrongPinMessage(failure.response.triesLeft);
  if (failure instanceof SessionEndedError) return failure.message;
  return failureMessage(failure, NO_INTERNET);
}

export function DeleteAccount({
  person,
  onClose,
}: {
  person: StoredPerson;
  onClose: () => void;
}) {
  const { colors } = useTheme();
  const { busy, lock } = useOperationLock();
  const delayed = useDelayedSubmit();
  const alive = useAlive();
  // The ref is what a press reads, so two quick presses never both see the same entry.
  const entry = useRef("");
  const [pin, setPin] = useState("");
  const [error, setError] = useState("");
  const [shake, setShake] = useState(0);
  const [sent, setSent] = useState(false);

  function show(next: string, message = "") {
    entry.current = next;
    setPin(next);
    setError(message);
  }

  function fail(message: string, wrong = false) {
    if (!alive()) return;
    show("", message);
    if (wrong) setShake((count) => count + 1);
  }

  async function submit(entered: string) {
    try {
      if (!(await confirmPin(person, entered)))
        return fail("Lock the app and sign in again, then ask once more.");
      const { status } = await apiSendResult(
        "POST",
        "setup/me/deletion-request",
        {},
      );
      if (!alive()) return;
      if (status === 202) setSent(true);
      else fail("The request could not be sent. Try again in a moment.");
    } catch (failure) {
      fail(messageFor(failure), isRefused(failure));
    } finally {
      lock.release();
    }
  }

  function press(digit: string) {
    if (lock.held() || entry.current.length >= person.pinLength) return;
    const entered = entry.current + digit;
    show(entered);
    if (entered.length === person.pinLength && lock.acquire())
      delayed.schedule(() => void submit(entered));
  }

  if (sent)
    return (
      <View style={styles.screen}>
        <Text weight="bold" accessibilityRole="header" style={styles.h1}>
          Request sent
        </Text>
        <Text style={{ color: colors.grey }}>
          Your administrator has been asked to delete your account. Until they
          do, you can keep using XCODE.
        </Text>
        <Button onPress={onClose}>Done</Button>
      </View>
    );

  return (
    <PinPad
      header={{
        kind: "heading",
        title: "Delete my account",
        sub: "Your administrator is asked to delete your account. They remove your name, mobile number and email from XCODE. Records you entered stay, shown as from a former member. Enter your PIN to send the request.",
      }}
      label="Your PIN"
      length={person.pinLength}
      value={pin}
      error={error}
      status={busy ? "Sending…" : ""}
      busy={busy}
      shake={shake}
      onDigit={press}
      onDelete={() => {
        if (!lock.held()) show(entry.current.slice(0, -1));
      }}
      links={
        <LinkRow>
          <LinkButton align="start" disabled={busy} onPress={onClose}>
            Cancel
          </LinkButton>
        </LinkRow>
      }
    />
  );
}

const styles = StyleSheet.create({
  screen: { gap: 16 },
  h1: { fontSize: 26, lineHeight: 31 },
});
