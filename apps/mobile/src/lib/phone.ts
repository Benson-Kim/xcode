// Kenyan mobile numbers as people type them: 0712 345 678.
export function normalisePhone(value: string) {
  let digits = (value || "").replace(/\D/g, "");
  if (digits.startsWith("254")) digits = "0" + digits.slice(3);
  else if (/^[17]/.test(digits)) digits = "0" + digits;
  return digits.slice(0, 10);
}

export function formatPhone(digits: string) {
  if (digits.length <= 4) return digits;
  if (digits.length <= 7) return `${digits.slice(0, 4)} ${digits.slice(4)}`;
  return `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}`;
}

export function maskPhone(digits: string) {
  return `${digits.slice(0, 4)} ••• ${digits.slice(7)}`;
}

export function phoneError(digits: string) {
  if (!digits) return "Enter your mobile number.";
  if (!/^0[17]\d{8}$/.test(digits))
    return "Enter all 10 numbers, starting 07 or 01.";
  return "";
}
