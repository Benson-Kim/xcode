-- Reverse 0024: any first day of the week is allowed again and Monday is the default; the stored first days stay Sunday, and the Sunday-week date goes.

SET LOCAL lock_timeout = '10s';

ALTER TABLE tenancy.organization_localizations
  ALTER COLUMN first_day_of_week SET DEFAULT 1,
  DROP CONSTRAINT ck_localizations_first_day_of_week,
  ADD CONSTRAINT ck_localizations_first_day_of_week CHECK (first_day_of_week BETWEEN 0 AND 6);

ALTER TABLE tenancy.organizations DROP COLUMN sunday_week_at;
