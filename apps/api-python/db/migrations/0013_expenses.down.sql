-- Reverse of 0013_expenses.sql (tables, columns and checks; routine bodies are the runner's). Refuses while change-log rows of the two new sections exist.

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tenancy.change_log WHERE section IN ('centralexpenses', 'reports')) THEN
    RAISE EXCEPTION 'change-log rows of the centralexpenses or reports sections exist; 0013 cannot be reversed over them';
  END IF;
END
$$;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_vehicle,
  ADD CONSTRAINT ck_change_log_vehicle CHECK (
    section = 'pettycash'
    OR (section IN ('vehicles', 'investment', 'revenue')) = (vehicle_id IS NOT NULL)
  ),
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn', 'pettycash'
  ));

ALTER TABLE pettycash.entries
  DROP CONSTRAINT ck_entries_group,
  DROP CONSTRAINT ck_entries_group_unit_amount,
  DROP CONSTRAINT ck_entries_group_units,
  DROP CONSTRAINT ck_entries_group_total,
  DROP CONSTRAINT uq_entries_group_vehicle,
  DROP COLUMN group_unit_amount,
  DROP COLUMN group_units,
  DROP COLUMN group_total,
  DROP COLUMN group_id;

DROP TABLE setup.saving_runs;
DROP TABLE setup.saving_opening_amounts;
DROP TABLE setup.saving_openings;
DROP TABLE setup.saving_run_states;

ALTER TABLE setup.recurring_versions
  DROP CONSTRAINT ck_recurring_versions_condition,
  DROP CONSTRAINT ck_recurring_versions_condition_days,
  DROP CONSTRAINT ck_recurring_versions_condition_min,
  DROP COLUMN condition_days,
  DROP COLUMN condition_min;

DROP TABLE setup.recurring_pauses;
DROP TABLE expenses.entries;
