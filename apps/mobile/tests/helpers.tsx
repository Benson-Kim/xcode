import { configure, fireEvent, render, screen } from "@testing-library/react-native";

import App from "../App";
import { savePerson, savePinCheck, saveSession, type StoredPerson } from "../src/lib/storage";
import { people } from "./fakeApi";

// Native host components are lazily transformed during the first query on a cold CI run.
configure({ asyncUtilTimeout: 10000 });

export async function startApp() {
  await render(<App />);
}

// Presses the keypad; after the last number the pad waits a moment before checking.
export async function typePin(pin: string) {
  for (const digit of pin) await fireEvent.press(screen.getByRole("button", { name: digit }));
}

// A phone that already signed in for this person: it holds their session, their details and a PIN check,
// in the shape a Phase 1 phone saved them (no wrong-PIN policy yet, so it reads as 5 tries and 15 minutes).
// `lastOnlineAt` left out keeps the Phase 1 shape, where the phone has no record of when it was last online.
export async function trustPhone(person: (typeof people)[keyof typeof people] = people.owner, phoneNumber = "0733520614", pin = "4826", lastOnlineAt?: number) {
  await saveSession({ phoneNumber, accessToken: "access-0", refreshToken: "refresh-0", ...(lastOnlineAt === undefined ? {} : { lastOnlineAt }) });
  await savePerson({ phoneNumber, firstName: person.firstName, lastName: person.lastName, role: person.role, permissions: person.permissions, pinLength: pin.length } as StoredPerson);
  await savePinCheck(pin);
}

export function storedText() {
  return [...(require("expo-secure-store").__items as Map<string, string>).values()].join(" ");
}
