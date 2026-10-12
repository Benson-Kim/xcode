-- Reverse of 0010_setup.sql. The weekly targets come back as they were before (sets saved since are lost, and vehicles added since have none); fleet numbers, initial investments and main categories are lost; a category saved without a bucket gets repairs and maintenance.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.setup_vehicle_create(
  uuid, uuid, text, uuid, text, text, date, numeric[], numeric, text, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_vehicle_update(
  uuid, uuid, text, uuid, uuid, text, text, date, numeric, text, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_expense_category_create(uuid, uuid, text, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_category_update(
  uuid, uuid, text, uuid, text, uuid, boolean, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_target_set_list(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_target_set_save(uuid, uuid, text, uuid, date, numeric[], timestamptz);
DROP FUNCTION IF EXISTS api.setup_target_set_remove(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_main_category_list(uuid, uuid, text, integer, integer, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_main_category_create(uuid, uuid, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_main_category_rename(uuid, uuid, text, uuid, text, timestamptz);
DROP FUNCTION IF EXISTS setup.target_set_on(uuid, date);
DROP FUNCTION IF EXISTS setup.day_target(uuid, date);
DROP FUNCTION IF EXISTS setup.week_total(setup.vehicle_target_sets);
DROP FUNCTION IF EXISTS setup.fleet_number(text);
DROP FUNCTION IF EXISTS setup.check_day_targets(numeric[]);
DROP FUNCTION IF EXISTS setup.expense_main_category_snapshot(uuid);

GRANT INSERT ON setup.vehicle_targets TO xcode_api_executor;
DROP TABLE setup.vehicle_target_sets;

UPDATE setup.expense_categories SET bucket = 1 WHERE bucket IS NULL;
DROP INDEX setup.ix_expense_categories_main_category;
ALTER TABLE setup.expense_categories
  DROP CONSTRAINT fk_expense_categories_main_category,
  DROP COLUMN main_category_id,
  ALTER COLUMN bucket SET NOT NULL;
DROP TABLE setup.expense_main_categories;

ALTER TABLE setup.fleet_vehicles
  DROP CONSTRAINT uq_fleet_vehicles_fleet_number,
  DROP CONSTRAINT ck_fleet_vehicles_initial_investment,
  DROP CONSTRAINT ck_fleet_vehicles_fleet_number,
  DROP COLUMN initial_investment,
  DROP COLUMN normalized_fleet_number,
  DROP COLUMN fleet_number;
