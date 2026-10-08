import { shiftDate } from "@xcode/shared/dates";

// Revenue dates are the organization's business dates ("2026-09-28"). They are only ever read from the API,
// never from the computer clock, and are handled as UTC calendar days.

export { shiftDate };
