import type { AuthenticatedPerson } from "@xcode/shared/auth";

import { apiGet } from "./lib/api";
import { DEFAULT_PIN_POLICY, loadPerson, savePerson, type StoredPerson } from "./lib/storage";

// The signed-in person from their session
export async function fetchPerson(
  phoneNumber: string,
  pinLength: number,
): Promise<StoredPerson> {
  const session = await apiGet<AuthenticatedPerson>("auth/session");

  const kept = await loadPerson();

  const policy = kept && (kept.userId ? kept.userId === session.userId : kept.phoneNumber === phoneNumber) ? kept : DEFAULT_PIN_POLICY;

  const person = {
    userId: session.userId,
    phoneNumber,
    firstName: session.firstName,
    lastName: session.lastName,
    role: session.role,
    permissions: session.permissions,
    pinLength,
    lockoutThreshold: policy.lockoutThreshold,
    lockoutMinutes: policy.lockoutMinutes,
  };

  await savePerson(person);

  return person;
}
