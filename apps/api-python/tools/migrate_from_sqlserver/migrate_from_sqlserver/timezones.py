"""Windows time-zone ids the .NET API may have stored, mapped to IANA names (question 18).

The entries are the CLDR ``windowsZones`` mappings for territory ``001`` of the zones this
business can plausibly use. An id that is neither an IANA name the target server knows nor
listed here is reported and the row is not loaded, so the owner decides it.
"""

from __future__ import annotations

WINDOWS_TO_IANA: dict[str, str] = {
    "UTC": "Etc/UTC",
    "GMT Standard Time": "Europe/London",
    "Greenwich Standard Time": "Atlantic/Reykjavik",
    "W. Europe Standard Time": "Europe/Berlin",
    "Romance Standard Time": "Europe/Paris",
    "Central Europe Standard Time": "Europe/Budapest",
    "Central European Standard Time": "Europe/Warsaw",
    "GTB Standard Time": "Europe/Bucharest",
    "E. Europe Standard Time": "Europe/Chisinau",
    "FLE Standard Time": "Europe/Kiev",
    "Russian Standard Time": "Europe/Moscow",
    "Turkey Standard Time": "Europe/Istanbul",
    "Israel Standard Time": "Asia/Jerusalem",
    "Egypt Standard Time": "Africa/Cairo",
    "South Africa Standard Time": "Africa/Johannesburg",
    "W. Central Africa Standard Time": "Africa/Lagos",
    "E. Africa Standard Time": "Africa/Nairobi",
    "Arab Standard Time": "Asia/Riyadh",
    "Arabian Standard Time": "Asia/Dubai",
    "Arabic Standard Time": "Asia/Baghdad",
    "Iran Standard Time": "Asia/Tehran",
    "Pakistan Standard Time": "Asia/Karachi",
    "India Standard Time": "Asia/Calcutta",
    "Bangladesh Standard Time": "Asia/Dhaka",
    "SE Asia Standard Time": "Asia/Bangkok",
    "China Standard Time": "Asia/Shanghai",
    "Singapore Standard Time": "Asia/Singapore",
    "Tokyo Standard Time": "Asia/Tokyo",
    "AUS Eastern Standard Time": "Australia/Sydney",
    "New Zealand Standard Time": "Pacific/Auckland",
    "Eastern Standard Time": "America/New_York",
    "Central Standard Time": "America/Chicago",
    "Mountain Standard Time": "America/Denver",
    "Pacific Standard Time": "America/Los_Angeles",
    "E. South America Standard Time": "America/Sao_Paulo",
}
