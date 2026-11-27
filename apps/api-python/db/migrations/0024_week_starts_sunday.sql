-- The week runs Sunday to Saturday for every organization (design notes Web v2.41): every localization's first day of the week becomes 0 (Sunday), 0 is the default and the only value allowed, and each organization that exists now records when its week moved, for the go-live notice.

SET LOCAL lock_timeout = '10s';

ALTER TABLE tenancy.organizations ADD COLUMN sunday_week_at timestamptz;

-- Organizations made later never had a Monday week, so they keep NULL and see no notice.
UPDATE tenancy.organizations SET sunday_week_at = now();

UPDATE tenancy.organization_localizations SET first_day_of_week = 0 WHERE first_day_of_week <> 0;

ALTER TABLE tenancy.organization_localizations
  ALTER COLUMN first_day_of_week SET DEFAULT 0,
  DROP CONSTRAINT ck_localizations_first_day_of_week,
  ADD CONSTRAINT ck_localizations_first_day_of_week CHECK (first_day_of_week = 0);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tenancy.organizations WHERE sunday_week_at IS NULL)
     OR EXISTS (SELECT 1 FROM tenancy.organization_localizations WHERE first_day_of_week <> 0) THEN
    RAISE EXCEPTION 'an organization has no Sunday-week date or a week that does not start on Sunday';
  END IF;
END;
$$;
