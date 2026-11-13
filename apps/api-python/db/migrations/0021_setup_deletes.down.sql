-- Reverse 0021: drop the setup delete routines and their refusal helper, then take back the executor's DELETE on the five setup tables. Deleted records stay deleted; the change log keeps what they held.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.setup_expense_main_category_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_category_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_item_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_vehicle_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.setup_company_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS setup.refuse_in_use(text, text, text);

REVOKE DELETE ON
  setup.expense_main_categories,
  setup.expense_categories,
  setup.expense_items,
  setup.fleet_vehicles,
  setup.psv_companies
FROM xcode_api_executor;
