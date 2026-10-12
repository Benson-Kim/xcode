-- Reverse of 0012_pettycash.sql. Change-log rows of the pettycash section stay, under constraints restored as NOT VALID.

SET LOCAL lock_timeout = '10s';

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_vehicle,
  ADD CONSTRAINT ck_change_log_vehicle CHECK (
    (section IN ('vehicles', 'investment', 'revenue')) = (vehicle_id IS NOT NULL)
  ) NOT VALID,
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn'
  )) NOT VALID;

DROP TABLE pettycash.entries;
DROP TABLE pettycash.statuses;
DROP TABLE pettycash.kinds;
