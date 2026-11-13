-- Setup deletes: the executor may delete expense main categories, categories, items, vehicles and companies, which the setup delete routines do only while no foreign key refers to the row (the routines turn the violation into the in_use refusal).

SET LOCAL lock_timeout = '10s';

GRANT DELETE ON
  setup.expense_main_categories,
  setup.expense_categories,
  setup.expense_items,
  setup.fleet_vehicles,
  setup.psv_companies
TO xcode_api_executor;
