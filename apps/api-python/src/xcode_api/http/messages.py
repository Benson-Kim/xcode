"""The message catalogue: every refusal code the routines and the service raise, with the
status it answers, the problem ``title`` and the sentence the clients show (``detail``),
parameters formatted from the routine's ``DETAIL`` (``docs/06-http-contract.md`` section 3).

This is the only place these strings live. A code that is not here reaches the client as a
500: an unknown code is a bug, never a sentence made up on the spot. Codes raised only to the
service or the CLI (``session_invalid``, ``rate_limit_invalid``, ``organization_not_single``)
have no entry on purpose.
"""

from __future__ import annotations

import string
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

FORBIDDEN_TITLE = "Not permitted in this organization or data scope."
NOT_FOUND_TITLE = "Record not found in your scope."
INVALID_TITLE = "Invalid setup change"
STALE_TITLE = "Settings changed. Reload before saving."
CONFLICT_TITLE = "A conflicting record exists. Reload before saving."


@dataclass(frozen=True, slots=True)
class Message:
    """How one refusal code answers. ``detail`` is a template whose ``{name}`` fields come
    from the routine's ``DETAIL``; ``extensions`` names the ``DETAIL`` keys copied onto the
    problem body (camelCase); ``plain`` bodies are ``{"detail": ...}`` with no title."""

    status: int
    title: str | None
    detail: str | None
    extensions: tuple[str, ...] = ()
    plain: bool = False

    def sentence(self, parameters: Mapping[str, Any]) -> str | None:
        if self.detail is None:
            return None
        return _FORMATTER.vformat(self.detail, (), _Parameters(parameters))


class _Parameters(dict[str, Any]):
    def __missing__(self, key: str) -> Any:
        raise KeyError(f"the refusal detail lacks the parameter {key!r}")


class _Formatter(string.Formatter):
    def format_field(self, value: Any, format_spec: str) -> str:
        return "" if value is None else super().format_field(value, format_spec)


_FORMATTER = _Formatter()


def _invalid(sentence: str, *extensions: str) -> Message:
    return Message(400, INVALID_TITLE, sentence, extensions)


def _forbidden(sentence: str) -> Message:
    return Message(403, FORBIDDEN_TITLE, sentence)


def _plain(status: int, sentence: str) -> Message:
    return Message(status, None, sentence, plain=True)


MESSAGES: Mapping[str, Message] = MappingProxyType(
    {
        # Cross-cutting
        "not_member": Message(403, FORBIDDEN_TITLE, None),
        "permission_missing": Message(403, FORBIDDEN_TITLE, None),
        "not_found": Message(404, NOT_FOUND_TITLE, None),
        "version_conflict": Message(409, STALE_TITLE, None),
        "unique_conflict": Message(409, CONFLICT_TITLE, None),
        "page_out_of_range": _invalid("Page must be 1\u2013100000 and page size 1\u2013100."),
        "reason_length": _invalid("A reason of 1\u2013500 characters is required."),
        "money_invalid": _invalid("Amount must be positive with at most two decimal places."),
        # People and access
        "people_names_required": _invalid("First and last name are required."),
        "people_email_invalid": _invalid("A valid email is required."),
        "people_phone_invalid": _invalid("A valid mobile number is required."),
        "people_scope_mode": _invalid("Choose a data scope."),
        "people_scope_empty": _invalid("Choose at least one item in the data scope."),
        "people_scope_duplicate": _invalid("Data scope items must be distinct."),
        "people_filter_status_invalid": _invalid(
            "Status must be active, not_signed_in, pin_reset_due, locked or blocked."
        ),
        "people_permissions_invalid": _invalid("Permissions and approval limit are invalid."),
        "people_role_unknown": _invalid("Unknown role."),
        "people_version_required": _invalid("Reload this person before saving."),
        "people_all_companies_needs_all": _forbidden(
            "Only someone who can see every company can give access to every company."
        ),
        "people_companies_unknown": _invalid("Choose companies in your organization."),
        "people_vehicles_unknown": _invalid("Choose vehicles in your organization."),
        "people_companies_outside_scope": _forbidden(
            "You can only give access to companies in your own data scope."
        ),
        "people_vehicles_outside_scope": _forbidden(
            "You can only give access to vehicles in your own data scope."
        ),
        "people_hidden_scope_kind": _forbidden(
            "This person's data scope includes companies or vehicles outside your own, so you cannot change which kind of scope they have. Their companies and vehicles outside your view are kept as they are."
        ),
        "people_self_edit": _invalid("You cannot change your own access here."),
        "people_owner_grant": _forbidden("Only an Owner can give the Owner role."),
        "people_owner_edit": _forbidden("Only an Owner can change, remove or sign out an Owner."),
        "people_permission_unknown": _invalid("Unknown permission."),
        "people_role_not_held": _forbidden("You can only grant roles whose permissions you hold."),
        "people_access_manage_needed": _forbidden(
            'Changing single permissions or an approval limit needs "Edit a person and their access".'
        ),
        "people_permission_not_held": _forbidden("You can only grant permissions you hold."),
        "people_sign_in_scope": _forbidden(
            "Only an Owner, or someone who can see this person's full data scope, can change their email or mobile number."
        ),
        "people_sign_in_holdings": _forbidden(
            "Only an Owner, or someone who holds everything this person holds, can change their email or mobile number."
        ),
        "people_contact_taken": _invalid("That mobile number or email already belongs to someone."),
        "people_self_deactivate": _invalid("You cannot deactivate your own access."),
        "people_self_sign_out": _invalid("Use sign out for your own session."),
        "people_self_sign_in": _invalid("Use the profile menu for your own PIN and devices."),
        "people_back_limit_invalid": _invalid(
            "Choose how far back this person can change records: none, 0 to 3650 days or 0 to 120 months."
        ),
        "people_back_limit_not_held": _forbidden(
            "You cannot let someone change records further back than you can."
        ),
        "people_back_limit_date_future": _invalid(
            "The date before which this person cannot change records cannot be after today."
        ),
        "record_too_old": _invalid(
            "You can only add or change records dated {earliest} or later.", "earliest"
        ),
        # Companies and vehicles
        "company_name_length": _invalid("Name must contain 1-160 characters."),
        "company_name_taken": _invalid("Another company already has this name."),
        "company_archived_rename": _invalid(
            "Archived companies cannot be renamed. Restore it first."
        ),
        "company_has_vehicles": _invalid(
            "Retire every vehicle in this company before archiving it."
        ),
        "company_already_archived": _invalid("The company is already archived."),
        "vehicle_registration_format": _invalid("Use the registration format KDA 482M."),
        "vehicle_joined_future": _invalid("A vehicle cannot join after the business date."),
        "vehicle_company_inactive": _invalid("Choose an active PSV company."),
        "vehicle_retired_edit": _invalid(
            "Retired vehicles must be restored before they can be edited."
        ),
        "vehicle_registration_change": _invalid(
            "Registration cannot change after a vehicle is added."
        ),
        "vehicle_registration_taken": _invalid("This registration already exists."),
        "vehicle_fleet_required": _invalid("Enter the fleet number."),
        "vehicle_fleet_length": _invalid("A fleet number has at most 20 characters."),
        "vehicle_fleet_taken": _invalid(
            "Fleet number {fleet} is already used in this PSV company."
        ),
        "target_start_required": _invalid("Enter the start date."),
        "target_days_required": _invalid("Enter the target for every day."),
        "target_start_past": _invalid("A target cannot start before today."),
        "target_set_unchanged": _invalid("This is the target already set for {date}."),
        "target_set_started": _invalid(
            "A target that has started cannot be changed or removed. Add a new one from today."
        ),
        "vehicle_join_after_revenue": _invalid(
            "{registration} has revenue recorded on {date}. A vehicle cannot join the fleet after a day it has a record for."
        ),
        "vehicle_leave_before_revenue": _invalid(
            "{registration} has revenue recorded on {date}. A vehicle cannot leave the fleet on or before a day it has a record for."
        ),
        "vehicle_leave_date_range": _invalid(
            "A vehicle's leave date must be from its join date through the business date."
        ),
        "vehicle_leave_before_return": _invalid(
            "A vehicle's leave date must be on or after the day it last returned to the fleet."
        ),
        "vehicle_already_retired": _invalid("The vehicle is already retired."),
        "vehicle_company_archived_restore": _invalid(
            "Restore the vehicle's archived company first."
        ),
        "vehicle_return_date_range": _invalid(
            "A vehicle's return date must be from the day it left through the business date."
        ),
        "report_period_invalid": _invalid("Period must be week or month."),
        "report_range_required": _invalid("Choose a period, or a from and through date."),
        "report_range_invalid": _invalid(
            "Report range must be at most 367 days and cannot include the future."
        ),
        # Scheduled items
        "recurring_savings_item": _invalid("Savings must not have an expense item."),
        "recurring_item_not_in_use": _invalid("Choose an expense item that is in use."),
        "recurring_schedule_shape": _invalid(
            "Choose a weekday (0\u20136), a month day (1\u201328 / last), or for yearly a month (1\u201312) and a day."
        ),
        "recurring_name_length": _invalid("Name must contain 1-160 characters."),
        "recurring_kind_invalid": _invalid(
            "Costs need an expense item; savings must not have one."
        ),
        "recurring_note_length": _invalid("A note can have at most 200 characters."),
        "recurring_filter_kind_invalid": _invalid("Kind must be cost or savings."),
        "recurring_filter_status_invalid": _invalid("Status must be running or stopped."),
        "recurring_end_before_start": _invalid("End date must be on or after start date."),
        "recurring_allocations_count": _invalid("Choose 1-500 distinct vehicles."),
        "recurring_allocation_sum": _invalid("Vehicle shares must equal the total exactly."),
        "recurring_daily_retired": _invalid(
            "Daily schedules are no longer offered. Choose weekly, monthly or yearly."
        ),
        "recurring_savings_frequency": _invalid("Savings are set aside weekly or monthly."),
        "recurring_cost_needs_item": _invalid("Choose the expense item this cost is for."),
        "recurring_start_required": _invalid("Start date is required."),
        "recurring_start_too_early": _invalid(
            "A schedule can start no earlier than the first of the current month."
        ),
        "recurring_share_inactive": _invalid(
            "New recurring shares must use active vehicles and companies."
        ),
        "recurring_stopped_edit": _invalid("Stopped items cannot be edited."),
        "recurring_running_start_change": _invalid(
            "An already running item's start date cannot change."
        ),
        "recurring_stop_confirm": _invalid(
            "Confirm stopping this item. Past postings are retained; no posting occurs from today."
        ),
        "recurring_stop_later_pending": _invalid(
            "This item is already due to stop on a later date. Cancel that stop first."
        ),
        "recurring_already_stopped": _invalid("The item is already stopped."),
        "recurring_stop_in_effect": _invalid(
            "This item has already stopped. Add a new scheduled item instead."
        ),
        # Change log, expense catalog, investment
        "history_dates_order": _invalid("The first date cannot be after the last date."),
        "history_text_length": _invalid("Search for 200 characters or fewer."),
        "history_before_invalid": _invalid("Before must be a change log version."),
        "expense_name_length": _invalid("Name must contain 1-100 characters."),
        "expense_category_taken": _invalid("That category already exists."),
        "expense_main_taken": _invalid("That main category already exists."),
        "expense_already_stopped": _invalid(
            "It is already turned off. Turn it on first to cancel that."
        ),
        "expense_item_taken": _invalid("That item already exists in this category."),
        "investment_date_invalid": _invalid(
            "An investment date is required and cannot be after the business date."
        ),
        "investment_description_length": _invalid("Say what it was, in 1-160 characters."),
        # Revenue
        "revenue_reason_invalid": _invalid("Choose a valid no-earnings reason."),
        "revenue_amount_with_reason": _invalid(
            "A reason is kept only for revenue below {currency} {threshold}."
        ),
        "revenue_entry_required": _invalid("Enter revenue or choose a no-earnings reason."),
        "revenue_low_needs_reason": _invalid(
            "Choose the reason. Revenue is below {currency} {threshold}."
        ),
        "revenue_note_length": _invalid("The no-earnings note must be at most 80 characters."),
        "revenue_note_without_other": _invalid("Only Other may have a no-earnings note."),
        "revenue_future_date": _invalid("Revenue cannot be recorded for a future date."),
        "revenue_vehicle_away": _invalid(
            "The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for."
        ),
        "revenue_vehicle_inactive": _invalid(
            "Revenue can only be recorded while the vehicle is active."
        ),
        "revenue_capture_permission": _forbidden(
            'Recording a day that has no record yet needs the permission "Capture revenue".'
        ),
        "revenue_correct_permission": _forbidden(
            'Changing revenue already saved needs the permission "Change revenue already saved".'
        ),
        "revenue_version_conflict": Message(
            409,
            "This day already has a different record.",
            "This day was changed after you opened it. Check the current record and save again.",
            ("current",),
        ),
        "revenue_concurrent_save": Message(
            409,
            "This day was changed by another save.",
            "Reload the current record and try again.",
        ),
        "revenue_week_range": _invalid(
            "Choose a week from the last ten years through the current week."
        ),
        "revenue_search_length": _invalid("Search for 40 characters or fewer."),
        "revenue_settings_invalid": _invalid(
            "The low-day threshold must be 0 or more and the amber band 0 to 100 per cent."
        ),
        "dashboard_period_invalid": _invalid("Period must be today, week or month."),
        # Organization, logo, preferences
        "organization_name_slug": _plain(
            400,
            "Enter an organization name and a lowercase slug using letters, numbers, and hyphens.",
        ),
        "organization_slug_taken": _plain(409, "This organization slug is already in use."),
        "settings_not_object": _invalid("Send the section's settings as an object."),
        "settings_wrong_type": _invalid("A setting has the wrong type of value."),
        "settings_business_date_future_zone": _invalid(
            "The held business date would be in the future in that time zone. Change the business date first."
        ),
        "business_date_invalid": _invalid("Business date must be a valid calendar date or null."),
        "business_date_future": _invalid("The business date cannot be in the future."),
        "locale_invalid": _invalid("Use BCP 47 locale."),
        "time_zone_invalid": _invalid(
            "'{value}' is an unknown or invalid time zone identifier. (Parameter 'value')"
        ),
        "format_settings_invalid": _invalid("Invalid format settings"),
        "brand_names_required": _invalid("Brand names and logo alt text are required."),
        "brand_colour_format": _invalid("Use a six-digit hex colour"),
        "brand_contrast": _invalid(
            "Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces"
        ),
        "brand_url_https": _invalid("Brand URLs must use HTTPS."),
        "brand_domain_invalid": _invalid("Invalid domain."),
        "brand_support_email_invalid": _invalid("Invalid support email."),
        "security_policy_pin_sign_in": _invalid("PIN sign-in cannot be disabled."),
        "security_policy_invalid": _invalid("Invalid security policy."),
        "logo_too_large": _invalid("The logo must be at most 256 KB."),
        "logo_type": _invalid("Upload a PNG, JPEG or WebP image."),
        "logo_unreadable": _invalid("The image could not be read."),
        "logo_signature": _invalid("The file is not the image type it claims to be."),
        "preferences_accessibility": _invalid("Invalid accessibility preferences"),
        "preferences_locale_not_allowed": _invalid(
            "Your organization does not allow a personal locale."
        ),
        "preferences_time_zone_not_allowed": _invalid(
            "Your organization does not allow a personal time zone."
        ),
        "preferences_hour12_not_allowed": _invalid(
            "Your organization does not allow a personal clock format."
        ),
        "preferences_theme_not_allowed": _invalid(
            "Your organization does not allow a personal theme."
        ),
        # Petty cash
        "pettycash_kind_invalid": _invalid("Choose an expense, a credit note or cash."),
        "pettycash_line_date_required": _invalid("Enter the date."),
        "pettycash_line_amount_zero": _invalid("Enter an amount other than zero."),
        "pettycash_line_amount_decimals": _invalid("Enter the amount with at most two decimals."),
        "pettycash_line_units": _invalid("Units must be above zero, with at most three decimals."),
        "pettycash_line_units_only_expense": _invalid("Only an expense has units."),
        "pettycash_line_total_zero": _invalid(
            "The total rounds to zero. Check the units and the amount.",
        ),
        "pettycash_line_total_large": _invalid("The total is too large."),
        "pettycash_line_note_length": _invalid("The note must be at most 80 characters."),
        "pettycash_line_vehicle_required": _invalid("Choose the vehicle."),
        "pettycash_line_item_required": _invalid("Choose what it was for."),
        "pettycash_line_expense_payee": _invalid("Only a credit note has a payee."),
        "pettycash_line_credit_vehicle": _invalid(
            "A credit note is not recorded against a vehicle.",
        ),
        "pettycash_line_payee_length": _invalid("The payee must be at most 80 characters."),
        "pettycash_line_cash_shape": _invalid("Cash given has only an amount, a date and a note."),
        "pettycash_spend_permission": _forbidden(
            'Recording spending needs the permission "Add an expense".',
        ),
        "pettycash_own_float_only": _invalid("Spending is recorded on your own float."),
        "pettycash_credit_permission": _forbidden(
            'Recording a credit note needs the permission "Record a credit note".',
        ),
        "pettycash_cash_permission": _forbidden(
            'Giving cash to a float needs the permission "Issue cash".',
        ),
        "pettycash_holder_required": _invalid("Choose who the cash goes to."),
        "pettycash_holder_not_holder": _invalid("Choose someone who keeps a petty cash float."),
        "pettycash_future_date": _invalid("Petty cash cannot be recorded for a future date."),
        "pettycash_too_old": _invalid("Choose a date in the last ten years."),
        "pettycash_range_both": _invalid("Choose the first and last day."),
        "pettycash_range_length": _invalid("Choose at most 367 days."),
        "pettycash_range_start": _invalid("Choose a period that starts on or before today."),
        "pettycash_vehicle_scope": _invalid("Choose one of your vehicles."),
        "pettycash_vehicle_inactive": _invalid("The vehicle was not in the fleet on that day."),
        "pettycash_item_inactive": _invalid("Choose an item that is in use."),
        "pettycash_below_zero": _invalid(
            'This takes the float below zero, which needs the permission "Issue cash to a float below zero".',
            "balance_after",
        ),
        "pettycash_change_cash": _invalid(
            "Cash given and credit notes cannot be changed. Delete the entry and record it again.",
        ),
        "pettycash_change_decided": _invalid("Reopen this entry before changing it."),
        "pettycash_change_own_permission": _forbidden(
            'Changing your own expenses needs the permission "Edit own expense".',
        ),
        "pettycash_change_other_permission": _forbidden(
            'Changing someone else\'s expense needs the permission "Edit any expense".',
        ),
        "pettycash_delete_cash_permission": _forbidden(
            'Deleting cash given or a credit note needs the permission "Delete a cash entry".',
        ),
        "pettycash_delete_rejected": _invalid("Reopen a rejected expense before deleting it."),
        "pettycash_delete_approved_permission": _forbidden(
            'Deleting an approved expense needs the permission "Delete after approval".',
        ),
        "pettycash_delete_own_permission": _forbidden(
            'Deleting your own expenses needs the permission "Delete own expense".',
        ),
        "pettycash_delete_other_permission": _forbidden(
            'Deleting someone else\'s expense needs the permission "Delete any expense".',
        ),
        "pettycash_cash_not_reviewed": _invalid("Cash given is not approved."),
        "pettycash_credit_not_reviewed": _invalid("A credit note is not approved."),
        "pettycash_own_float_review": _forbidden(
            "You cannot approve, send back or reject entries on your own float.",
        ),
        "pettycash_own_entry_review": _forbidden(
            "You cannot approve, send back or reject an entry you recorded.",
        ),
        "pettycash_above_limit": _forbidden("This entry is above your approval limit."),
        "pettycash_not_waiting": _invalid(
            "Only an entry waiting for approval can be approved, sent back or rejected.",
        ),
        "pettycash_sent_back": _invalid(
            "This entry was sent back. It can be approved once it is saved again.",
        ),
        "pettycash_already_sent_back": _invalid("This entry was already sent back."),
        "pettycash_not_decided": _invalid("Only an approved or rejected entry can be reopened."),
        "pettycash_kind_change": _invalid(
            "An entry cannot change between expense, credit note and cash. Remove it and record it again.",
        ),
        "pettycash_holder_change": _invalid(
            "An entry cannot move to another float. Remove it and record it again.",
        ),
        "pettycash_comment_required": _invalid("Say what should be fixed."),
        "pettycash_comment_length": _invalid("The comment must be at most 200 characters."),
        "pettycash_reject_reason_required": _invalid("Say why the entry is rejected."),
        "pettycash_reopen_reason_required": _invalid("Say why the entry is reopened."),
        "pettycash_decision_reason_length": _invalid("The reason must be at most 200 characters."),
        "pettycash_approve_none": _invalid("Choose the entries to approve."),
        "pettycash_approve_many": _invalid("Approve at most 100 entries at a time."),
        "pettycash_period_invalid": _invalid("Choose a day or a week."),
        "pettycash_status_invalid": _invalid(
            "Status must be waiting, approved, sentBack or rejected.",
        ),
        "pettycash_entry_changed": Message(
            409,
            "This entry has changed.",
            "This entry was changed after you opened it. Check it and save again.",
            ("current",),
        ),
        "pettycash_already_saved": Message(
            409,
            "This entry has changed.",
            "This entry was already saved by someone else. Reload and try again.",
            ("current",),
        ),
        "pettycash_concurrent_save": Message(
            409, "This entry was changed by another save.", "Reload and try again."
        ),
    }
)


def message_for(code: str) -> Message | None:
    return MESSAGES.get(code)
