// Display formats shared by the setup screens.

export function kes(amount: number) {
  return `KES ${amount.toLocaleString("en-GB", { maximumFractionDigits: 2 })}`;
}

export function plural(count: number, one: string, many: string) {
  return `${count} ${count === 1 ? one : many}`;
}

// +254712345678 -> 0712 345 678, the way people write Kenyan numbers.
export function formatPhone(value: string) {
  const digits = value.replace(/\D/g, "");
  const local = digits.startsWith("254") ? `0${digits.slice(3)}` : digits;
  return local.length === 10 ? `${local.slice(0, 4)} ${local.slice(4, 7)} ${local.slice(7)}` : value;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "20 Sep 2026 16:05" in the viewer's local time, as the design writes timestamps.
export function formatDateTime(value: string) {
  const date = new Date(value);
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()} ${time}`;
}

export function initials(firstName: string, lastName: string) {
  return `${firstName.charAt(0)}${lastName.charAt(0)}`.toUpperCase();
}
