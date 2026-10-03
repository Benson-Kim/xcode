import { apiGet } from "./lib/api";
import { DEFAULT_PIN_POLICY, loadPerson, savePerson, type StoredPerson } from "./lib/storage";

type AuthSession = {
  userId: string;
  firstName: string;
  lastName: string;
  role: string;
  permissions: string[];
};

// The signed-in person from their sessio
export async function fetchPerson(
  phoneNumber: string,
  pinLength: number,
): Promise<StoredPerson> {
  const session = await apiGet<AuthSession>("auth/session");
  // The wrong-PIN policy comes with the appearance; keep what this phone already has for the number.
  const kept = await loadPerson();
  // The same account by its id (its number may have changed), or by number for a record saved before ids were kept.
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

export const initials = (
  person: Pick<StoredPerson, "firstName" | "lastName">,
) => `${person.firstName.charAt(0)}${person.lastName.charAt(0)}`.toUpperCase();
