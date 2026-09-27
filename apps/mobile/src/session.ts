import { apiGet } from "./lib/api";
import { savePerson, type StoredPerson } from "./lib/storage";

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
  const person = {
    phoneNumber,
    firstName: session.firstName,
    lastName: session.lastName,
    role: session.role,
    permissions: session.permissions,
    pinLength,
  };
  await savePerson(person);
  return person;
}

export const initials = (
  person: Pick<StoredPerson, "firstName" | "lastName">,
) => `${person.firstName.charAt(0)}${person.lastName.charAt(0)}`.toUpperCase();
