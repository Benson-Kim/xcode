"""Organization settings, appearance and preferences contract models
(``docs/inventory/inventory-http-contract.md`` section 3.7): field order is the wire order.

The settings read serves ``useGrouping`` only; the effective formats (appearance and the
settings read's ``effective``) also serve the legacy ``useGroupping`` for released apps, and a
localization save accepts it (the current name wins, decided by the routine)."""

from __future__ import annotations

import math
from datetime import date
from typing import Annotated, Any
from uuid import UUID

from pydantic import AfterValidator, computed_field

from ...domain.tenancy import SettingsSection
from .common import ApiModel, Money


class OrganizationDto(ApiModel):
    id: UUID
    slug: str
    name: str
    business_date: date | None
    settings_version: int


class LocalizationDto(ApiModel):
    organization_id: UUID
    locale: str
    time_zone: str
    date_pattern: str
    hour12: bool
    first_day_of_week: int
    week_numbering: str
    currency: str
    use_grouping: bool
    number_decimals: int
    allow_locale_override: bool
    allow_time_zone_override: bool
    allow_hour12_override: bool
    allow_theme_override: bool


class BrandingDto(ApiModel):
    organization_id: UUID
    display_name: str
    legal_name: str
    logo_light: str | None
    logo_dark: str | None
    logo_alt: str
    favicon: str | None
    primary: str
    secondary: str
    accent: str
    domain: str | None
    support_email: str | None
    terms_url: str | None
    privacy_url: str | None


class SecurityPolicyDto(ApiModel):
    organization_id: UUID
    password_min_length: int
    password_complexity: bool
    password_history: int
    pin_length: int
    lockout_threshold: int
    lockout_minutes: int
    access_token_minutes: int
    refresh_token_days: int
    idle_unlock_seconds: int
    allow_pin_sign_in: bool


class RevenueSettingsDto(ApiModel):
    organization_id: UUID
    low_day_threshold: Money
    gap_amber_percent: Money


class EffectiveFormats(ApiModel):
    locale: str
    time_zone: str
    date_pattern: str
    hour12: bool
    first_day_of_week: int
    week_numbering: str
    currency: str
    use_grouping: bool
    number_decimals: int
    direction: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def use_groupping(self) -> bool:
        """The misspelt name released apps still read, beside ``useGrouping``."""
        return self.use_grouping


class EffectiveSettings(ApiModel):
    formats: EffectiveFormats
    branding: BrandingDto
    security_policy: SecurityPolicyDto
    theme_mode: str
    reduced_motion: bool
    font_scale: float


class OrganizationSettingsResponse(ApiModel):
    organization: OrganizationDto
    localization: LocalizationDto
    branding: BrandingDto
    security_policy: SecurityPolicyDto
    effective_business_date: date
    calendar_date: date
    effective: EffectiveSettings
    revenue: RevenueSettingsDto


def _finite(value: Any) -> Any:
    """Python reads ``Infinity``, ``NaN`` and numbers like ``1e999`` as non-finite floats,
    which no JSON document holds: a field refusal here, not a 500 at the database."""
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("numbers must be finite")
    if isinstance(value, dict):
        for item in value.values():
            _finite(item)
    elif isinstance(value, list):
        for item in value:
            _finite(item)
    return value


class SaveOrganizationSettings(ApiModel):
    """``value`` is any JSON: an object for the merged sections, ``{name, slug}`` for the
    organization, a ``yyyy-MM-dd`` string or ``null`` for the business date."""

    value: Annotated[Any, AfterValidator(_finite)] = None
    reason: str | None = None

    def document_value(self, section: str) -> Any:
        """``value`` with its top-level camelCase keys renamed to the document keys the
        routine merges; keys the section does not have are dropped (they would be ignored)."""
        keys = _DOCUMENT_KEYS.get(section)
        if keys is None or not isinstance(self.value, dict):
            return self.value
        return {keys[name]: item for name, item in self.value.items() if name in keys}


class SettingsSectionResponse(ApiModel):
    section: str


class SaveLogo(ApiModel):
    data_url: str
    reason: str | None = None


class LogoResponse(ApiModel):
    logo: str | None


class AppearanceBranding(ApiModel):
    display_name: str
    logo_alt: str
    primary: str
    secondary: str
    accent: str
    logo: str | None


class AppearanceResponse(ApiModel):
    organization_name: str
    settings_version: int
    business_date: date
    branding: AppearanceBranding
    formats: EffectiveFormats
    theme_mode: str
    reduced_motion: bool
    font_scale: float
    lockout_threshold: int
    lockout_minutes: int
    idle_unlock_seconds: int


class UserPreferenceDto(ApiModel):
    organization_id: UUID
    user_id: UUID
    locale: str | None
    time_zone: str | None
    hour12: bool | None
    theme_mode: str | None
    reduced_motion: bool
    font_scale: float


class PreferenceDefaults(ApiModel):
    locale: str
    time_zone: str
    hour12: bool


class PreferencesResponse(ApiModel):
    organization_id: UUID
    user_id: UUID
    locale: str | None
    time_zone: str | None
    hour12: bool | None
    theme_mode: str | None
    reduced_motion: bool
    font_scale: float
    allow_locale_override: bool
    allow_time_zone_override: bool
    allow_hour12_override: bool
    allow_theme_override: bool
    organization: PreferenceDefaults


class SaveUserPreferences(ApiModel):
    """``PUT /setup/preferences``; extra fields (the web sends the whole read back) are
    ignored, and an omitted ``fontScale`` is 0, which the routine refuses."""

    locale: str | None = None
    time_zone: str | None = None
    hour12: bool | None = None
    theme_mode: str | None = None
    reduced_motion: bool = False
    font_scale: float = 0


def _aliases(model: type[ApiModel]) -> dict[str, str]:
    return {
        field.alias or name: name
        for name, field in model.model_fields.items()
        if name != "organization_id"
    }


_DOCUMENT_KEYS: dict[str, dict[str, str]] = {
    SettingsSection.ORGANIZATION: {"name": "name", "slug": "slug"},
    SettingsSection.LOCALIZATION: {**_aliases(LocalizationDto), "useGroupping": "use_groupping"},
    SettingsSection.BRANDING: _aliases(BrandingDto),
    SettingsSection.SECURITY_POLICY: _aliases(SecurityPolicyDto),
    SettingsSection.REVENUE: _aliases(RevenueSettingsDto),
}
