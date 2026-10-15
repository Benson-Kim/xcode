-- Reverse of 0005_setup.sql.

SET LOCAL lock_timeout = '10s';

REVOKE USAGE ON SCHEMA setup FROM xcode_readonly;
ALTER TABLE tenancy.data_scope_vehicles DROP CONSTRAINT fk_data_scope_vehicles_vehicle;
ALTER TABLE tenancy.data_scope_companies DROP CONSTRAINT fk_data_scope_companies_company;
DROP TABLE setup.recurring_allocations;
DROP TABLE setup.recurring_versions;
DROP TABLE setup.recurring_items;
DROP TABLE setup.expense_items;
DROP TABLE setup.expense_categories;
DROP TABLE setup.vehicle_investments;
DROP TABLE setup.vehicle_away_periods;
DROP TABLE setup.vehicle_targets;
DROP TABLE setup.fleet_vehicles;
DROP TABLE setup.psv_companies;
DROP TABLE setup.expense_buckets;
DROP TABLE setup.recurrence_frequencies;
DROP TABLE setup.recurring_kinds;
DROP FUNCTION setup.check_allocation_sum();
DROP FUNCTION setup.forbid_registration_change();
DROP EXTENSION btree_gist;
