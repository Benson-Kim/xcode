-- Synthetic rows for the legacy fixture: every rule of docs/10 7.3 and 7.4 has a row here.
-- No row comes from production. The rows go in through the old application's own triggers,
-- which derive names, signs, copies of committed petty-cash expenses and daily balances.
-- Days are relative to the last full month before the run (d(n) = its first day + n), so the
-- check through setup.fleet_postings always has postings to compare.

SET search_path = public;

CREATE FUNCTION pg_temp.d(n integer) RETURNS date LANGUAGE sql AS $$
  SELECT (date_trunc('month', (now() AT TIME ZONE 'Africa/Nairobi')::date) - interval '1 month')::date + n
$$;
CREATE FUNCTION pg_temp.t(n integer, at time) RETURNS timestamptz LANGUAGE sql AS $$
  SELECT (pg_temp.d(n) + at) AT TIME ZONE 'Africa/Nairobi'
$$;

INSERT INTO alembic_version (version_num) VALUES ('d8e1a4f9c220');

INSERT INTO permissions (id, title)
SELECT ('90000000-0000-4000-8000-' || lpad(n::text, 12, '0'))::uuid, title
FROM unnest(ARRAY[
  'budgets:read', 'budgets:write', 'categories:delete', 'categories:read', 'categories:write',
  'dashboard:financial', 'dashboard:overview', 'dashboard:petty_cash', 'dashboard:read',
  'dashboard:vehicles', 'entries:delete', 'entries:read', 'entries:write', 'permissions:read',
  'petty_cash:commit', 'petty_cash:delete', 'petty_cash:read', 'petty_cash:reconcile',
  'petty_cash:write_cash', 'petty_cash:write_credit_note', 'petty_cash:write_expense',
  'provisions:delete', 'provisions:read', 'provisions:write', 'records:delete', 'records:lock',
  'records:read', 'records:write', 'reports:budget', 'reports:expenses', 'reports:export',
  'reports:income', 'reports:petty_cash', 'reports:print', 'reports:read', 'roles:delete',
  'roles:read', 'roles:write', 'statements:read', 'users:read', 'users:write', 'vehicles:read',
  'vehicles:write'
]) WITH ORDINALITY AS p (title, n);

INSERT INTO roles (id, title, is_system_role, permissions) VALUES
  ('80000000-0000-4000-8000-000000000001', 'Administrator', true,
   (SELECT array_agg(id ORDER BY title) FROM permissions)),
  ('80000000-0000-4000-8000-000000000002', 'Manager 101', false,
   (SELECT array_agg(id ORDER BY title) FROM permissions WHERE title IN (
     'categories:read', 'categories:write', 'dashboard:financial', 'dashboard:overview',
     'dashboard:petty_cash', 'dashboard:read', 'dashboard:vehicles', 'entries:read',
     'entries:write', 'petty_cash:read', 'petty_cash:reconcile', 'petty_cash:write_expense',
     'records:delete', 'records:read', 'records:write', 'reports:budget', 'reports:expenses',
     'reports:export', 'reports:income', 'reports:petty_cash', 'reports:print', 'reports:read',
     'statements:read', 'vehicles:read', 'vehicles:write'))),
  ('80000000-0000-4000-8000-000000000003', 'Manager 1', false, '{}');

-- People: the author of old entries; a one-word Administrator without a number; a Manager 101
-- whose e-mail and role --people change; the default petty-cash manager (the float holder);
-- another manager; a person whose role holds no permission.
INSERT INTO users (id, name, email, password, phone, role_id, is_default_petty_cash_manager,
                   petty_cash_backdate_days, created_at, updated_at) VALUES
  ('a0000000-0000-4000-8000-000000000001', 'Ada Lovelace', 'ada@legacy.example',
   '$2b$12$fixture.not.a.hash', '0711000001', '80000000-0000-4000-8000-000000000001', false, 180,
   pg_temp.t(-60, '09:00'), pg_temp.t(-60, '09:00')),
  ('a0000000-0000-4000-8000-000000000002', 'Hypatia', 'hypatia@legacy.example',
   '$2b$12$fixture.not.a.hash', NULL, '80000000-0000-4000-8000-000000000001', false, 7,
   pg_temp.t(-59, '09:00'), pg_temp.t(-59, '09:00')),
  ('a0000000-0000-4000-8000-000000000003', 'Grace Brewster Hopper', 'Grace@Legacy.example',
   '$2b$12$fixture.not.a.hash', '0711 000 003', '80000000-0000-4000-8000-000000000002', false, 45,
   pg_temp.t(-58, '09:00'), pg_temp.t(-58, '09:00')),
  ('a0000000-0000-4000-8000-000000000004', 'Mary Seacole', 'mary@legacy.example',
   '$2b$12$fixture.not.a.hash', '0711000004', '80000000-0000-4000-8000-000000000002', true, 90,
   pg_temp.t(-57, '09:00'), pg_temp.t(-57, '09:00')),
  ('a0000000-0000-4000-8000-000000000005', 'Alan Turing', 'alan@legacy.example',
   '$2b$12$fixture.not.a.hash', '0711000005', '80000000-0000-4000-8000-000000000002', false, 7,
   pg_temp.t(-56, '09:00'), pg_temp.t(-56, '09:00')),
  ('a0000000-0000-4000-8000-000000000006', 'Nikola Tesla', 'nikola@legacy.example',
   '$2b$12$fixture.not.a.hash', '0711000006', '80000000-0000-4000-8000-000000000003', false, 7,
   pg_temp.t(-55, '09:00'), pg_temp.t(-55, '09:00'));

INSERT INTO categories (id, title, factor, created_at, updated_at) VALUES
  ('c0000000-0000-4000-8000-000000000001', 'Income', 'plus', pg_temp.t(-90, '08:00'), pg_temp.t(-90, '08:00')),
  ('c0000000-0000-4000-8000-000000000002', 'Repairs', 'minus', pg_temp.t(-90, '08:01'), pg_temp.t(-90, '08:01')),
  ('c0000000-0000-4000-8000-000000000003', 'Fuel', 'minus', pg_temp.t(-90, '08:02'), pg_temp.t(-90, '08:02')),
  ('c0000000-0000-4000-8000-000000000004', 'Body Works ', 'minus', pg_temp.t(-90, '08:03'), pg_temp.t(-90, '08:03'));

-- Items: Earnings and an unused plus item (not moved); a duplicate name inside a category
-- (merged into the first); two items without a category (their deductions held back).
INSERT INTO entries (id, title, factor, category_id, position, "primary", created_at, updated_at) VALUES
  ('d0000000-0000-4000-8000-000000000001', 'Earnings', 'plus', 'c0000000-0000-4000-8000-000000000001', 1, true, pg_temp.t(-90, '09:00'), pg_temp.t(-90, '09:00')),
  ('d0000000-0000-4000-8000-000000000002', 'Daily Offload', 'plus', NULL, 2, false, pg_temp.t(-90, '09:01'), pg_temp.t(-90, '09:01')),
  ('d0000000-0000-4000-8000-000000000003', 'Diesel', 'minus', 'c0000000-0000-4000-8000-000000000003', 3, false, pg_temp.t(-90, '09:02'), pg_temp.t(-90, '09:02')),
  ('d0000000-0000-4000-8000-000000000004', 'Oil Change', 'minus', 'c0000000-0000-4000-8000-000000000002', 4, false, pg_temp.t(-90, '09:03'), pg_temp.t(-90, '09:03')),
  ('d0000000-0000-4000-8000-000000000005', 'Body Branding', 'minus', 'c0000000-0000-4000-8000-000000000004', 5, false, pg_temp.t(-90, '09:04'), pg_temp.t(-90, '09:04')),
  ('d0000000-0000-4000-8000-000000000006', 'Body branding', 'minus', 'c0000000-0000-4000-8000-000000000004', 6, false, pg_temp.t(-80, '09:05'), pg_temp.t(-80, '09:05')),
  ('d0000000-0000-4000-8000-000000000007', 'Savings', 'minus', NULL, 7, false, pg_temp.t(-90, '09:06'), pg_temp.t(-90, '09:06')),
  ('d0000000-0000-4000-8000-000000000008', 'Sacco', 'minus', NULL, 8, false, pg_temp.t(-90, '09:07'), pg_temp.t(-90, '09:07'));

-- Vehicles: one registration with its space, one without, one in lower case; two spellings of
-- one sacco; the first vehicle has revenue from before it was created.
INSERT INTO vehicles (id, registration, sacco, created_at, updated_at) VALUES
  ('b0000000-0000-4000-8000-000000000001', 'KAA 111A', 'alpha sacco ', pg_temp.t(1, '08:00'), pg_temp.t(1, '08:00')),
  ('b0000000-0000-4000-8000-000000000002', 'KBB222B', 'Alpha Sacco', pg_temp.t(-10, '08:00'), pg_temp.t(-10, '08:00')),
  ('b0000000-0000-4000-8000-000000000003', 'kcc 333c', 'Beta Sacco', pg_temp.t(1, '08:30'), pg_temp.t(1, '08:30'));

INSERT INTO provisions (id, vehicle_id, amount, entry_type, date, description, created_at, updated_at) VALUES
  ('70000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000001', 1000, 'DEPOSIT', pg_temp.d(9), 'Opening deposit', pg_temp.t(9, '10:00'), pg_temp.t(9, '10:00'));

-- Revenue: a day entered twice with the same amount (the first is kept), a day saved as 0, a
-- day in cents, a day with two different amounts (held back), a day before the vehicle was
-- created. Direct deductions: one that moves, three on items without a category, one on the
-- merged item (two units), one whose amount does not divide by its quantity.
INSERT INTO records (id, entry_id, vehicle_id, amount, quantity, date, created_at, updated_at) VALUES
  ('e0000000-0000-4000-8000-000000000001', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000001', 10000, 1, pg_temp.d(1), pg_temp.t(1, '18:00'), pg_temp.t(1, '18:00')),
  ('e0000000-0000-4000-8000-000000000002', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000001', 10000, 1, pg_temp.d(1), pg_temp.t(1, '18:05'), pg_temp.t(1, '18:05')),
  ('e0000000-0000-4000-8000-000000000003', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000002', 0, 1, pg_temp.d(1), pg_temp.t(1, '18:10'), pg_temp.t(1, '18:10')),
  ('e0000000-0000-4000-8000-000000000004', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000003', 7500.5, 1, pg_temp.d(9), pg_temp.t(9, '18:00'), pg_temp.t(9, '19:00')),
  ('e0000000-0000-4000-8000-000000000005', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000002', 5000, 1, pg_temp.d(9), pg_temp.t(9, '18:00'), pg_temp.t(9, '18:00')),
  ('e0000000-0000-4000-8000-000000000006', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000002', 6000, 1, pg_temp.d(9), pg_temp.t(9, '18:30'), pg_temp.t(9, '18:30')),
  ('e0000000-0000-4000-8000-000000000007', 'd0000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000001', 8000, 1, pg_temp.d(-5), pg_temp.t(-5, '18:00'), pg_temp.t(-5, '18:00')),
  ('e0000000-0000-4000-8000-000000000011', 'd0000000-0000-4000-8000-000000000004', 'b0000000-0000-4000-8000-000000000001', 1200, 1, pg_temp.d(1), pg_temp.t(1, '12:00'), pg_temp.t(1, '12:00')),
  ('e0000000-0000-4000-8000-000000000012', 'd0000000-0000-4000-8000-000000000007', 'b0000000-0000-4000-8000-000000000002', 500, 1, pg_temp.d(1), pg_temp.t(1, '12:05'), pg_temp.t(1, '12:05')),
  ('e0000000-0000-4000-8000-000000000013', 'd0000000-0000-4000-8000-000000000008', 'b0000000-0000-4000-8000-000000000003', 300, 1, pg_temp.d(9), pg_temp.t(9, '12:00'), pg_temp.t(9, '12:00')),
  ('e0000000-0000-4000-8000-000000000014', 'd0000000-0000-4000-8000-000000000007', 'b0000000-0000-4000-8000-000000000003', 250, 1, pg_temp.d(19), pg_temp.t(19, '12:00'), pg_temp.t(19, '12:00')),
  ('e0000000-0000-4000-8000-000000000015', 'd0000000-0000-4000-8000-000000000006', 'b0000000-0000-4000-8000-000000000001', 1000, 2, pg_temp.d(9), pg_temp.t(9, '12:30'), pg_temp.t(9, '12:30')),
  ('e0000000-0000-4000-8000-000000000016', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000002', 100, 3, pg_temp.d(19), pg_temp.t(19, '12:30'), pg_temp.t(19, '12:30'));

-- Petty cash, in day order (the old trigger computes each day's balance as rows arrive): cash
-- received twice alike, cash of 0, cash in fractions of a cent; committed and waiting
-- expenses, one repeated, one of 0, one without a vehicle, one on the merged item, one of half a
-- unit, one whose amount has a third decimal (1.5 x 10.25 = 15.375, exact in double), one
-- whose amount carries the double's noise (4.5 x 33.33); a credit note with a payee and one
-- with the old application's generic label. Managers: none, the default one, another.
INSERT INTO petty_cash (id, name, entry_id, vehicle_id, plus, unit_price, quantity, date, committed, credit_note, source, description, manager_id, created_at, updated_at) VALUES
  ('f0000000-0000-4000-8000-000000000001', 'Float top-up', NULL, NULL, 50000, NULL, NULL, pg_temp.d(1), false, false, NULL, NULL, NULL, pg_temp.t(1, '07:00'), pg_temp.t(1, '07:00')),
  ('f0000000-0000-4000-8000-000000000002', 'Float top-up', NULL, NULL, 50000, NULL, NULL, pg_temp.d(1), false, false, NULL, NULL, NULL, pg_temp.t(1, '07:02'), pg_temp.t(1, '07:02')),
  ('f0000000-0000-4000-8000-000000000013', 'Cash Received', NULL, NULL, 50000, NULL, NULL, pg_temp.d(1), true, false, NULL, NULL, NULL, pg_temp.t(1, '07:05'), pg_temp.t(1, '07:05')),
  ('f0000000-0000-4000-8000-000000000005', 'x', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000001', NULL, 1500, 2, pg_temp.d(1), true, false, NULL, NULL, NULL, pg_temp.t(1, '09:00'), pg_temp.t(1, '17:00')),
  ('f0000000-0000-4000-8000-000000000006', 'x', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000001', NULL, 1500, 2, pg_temp.d(1), true, false, NULL, NULL, NULL, pg_temp.t(1, '09:03'), pg_temp.t(1, '17:00')),
  ('f0000000-0000-4000-8000-000000000008', 'x', 'd0000000-0000-4000-8000-000000000005', NULL, NULL, 30000, 1, pg_temp.d(1), false, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(1, '10:00'), pg_temp.t(1, '10:00'));
INSERT INTO petty_cash (id, name, entry_id, vehicle_id, plus, unit_price, quantity, date, committed, credit_note, source, description, manager_id, created_at, updated_at) VALUES
  ('f0000000-0000-4000-8000-000000000003', 'Cash Received', NULL, NULL, 0, NULL, NULL, pg_temp.d(9), true, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(9, '07:00'), pg_temp.t(9, '07:00')),
  ('f0000000-0000-4000-8000-000000000007', 'x', 'd0000000-0000-4000-8000-000000000004', 'b0000000-0000-4000-8000-000000000002', NULL, 2000, 1, pg_temp.d(9), false, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000005', pg_temp.t(9, '09:00'), pg_temp.t(9, '09:00')),
  ('f0000000-0000-4000-8000-000000000009', 'x', 'd0000000-0000-4000-8000-000000000006', 'b0000000-0000-4000-8000-000000000003', NULL, 700, 1, pg_temp.d(9), true, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(9, '09:30'), pg_temp.t(9, '16:00')),
  ('f0000000-0000-4000-8000-000000000010', 'x', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000002', NULL, 0, 1, pg_temp.d(9), true, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(9, '10:00'), pg_temp.t(9, '16:00')),
  ('f0000000-0000-4000-8000-000000000015', 'x', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000003', NULL, 10.25, 1.5, pg_temp.d(9), false, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(9, '11:00'), pg_temp.t(9, '11:00')),
  ('f0000000-0000-4000-8000-000000000016', 'x', 'd0000000-0000-4000-8000-000000000003', 'b0000000-0000-4000-8000-000000000003', NULL, 33.33, 4.5, pg_temp.d(9), false, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(9, '11:30'), pg_temp.t(9, '11:30'));
INSERT INTO petty_cash (id, name, entry_id, vehicle_id, plus, unit_price, quantity, date, committed, credit_note, source, description, manager_id, created_at, updated_at) VALUES
  ('f0000000-0000-4000-8000-000000000004', 'Odd cents', NULL, NULL, 12345.675, NULL, NULL, pg_temp.d(19), false, false, 'Odd cents', NULL, 'a0000000-0000-4000-8000-000000000005', pg_temp.t(19, '07:00'), pg_temp.t(19, '07:00')),
  ('f0000000-0000-4000-8000-000000000011', 'x', 'd0000000-0000-4000-8000-000000000004', 'b0000000-0000-4000-8000-000000000003', NULL, 1000, 0.5, pg_temp.d(19), false, false, NULL, NULL, 'a0000000-0000-4000-8000-000000000004', pg_temp.t(19, '09:00'), pg_temp.t(19, '09:00'));
INSERT INTO petty_cash (id, name, entry_id, vehicle_id, minus, date, committed, credit_note, source, description, manager_id, created_at, updated_at) VALUES
  ('f0000000-0000-4000-8000-000000000012', 'Credit Note', NULL, NULL, 4000, pg_temp.d(19), false, true, 'Payee Fixture Hardware', 'Returned part', 'a0000000-0000-4000-8000-000000000004', pg_temp.t(19, '11:00'), pg_temp.t(19, '11:00')),
  ('f0000000-0000-4000-8000-000000000014', 'Credit Note', NULL, NULL, 2500, pg_temp.d(19), false, true, 'Credit Note', 'Insurance 111', 'a0000000-0000-4000-8000-000000000004', pg_temp.t(19, '11:30'), pg_temp.t(19, '11:30'));

-- The stored daily balances go wrong as the old trigger's did: a stored row on a day without
-- entries reads 500 too much (the next day is right again), and from d(19) the balance is
-- 1,000 short.
INSERT INTO petty_cash_daily_balances (id, date, opening_balance, closing_balance)
SELECT '50000000-0000-4000-8000-000000000001', pg_temp.d(12), b.closing_balance + 500, b.closing_balance + 500
FROM petty_cash_daily_balances AS b WHERE b.date = pg_temp.d(9);
UPDATE petty_cash_daily_balances SET opening_balance = opening_balance - 1000, closing_balance = closing_balance - 1000
WHERE date >= pg_temp.d(19);

INSERT INTO budgets (id, vehicle_id, category_id, year, month, budget) VALUES
  ('60000000-0000-4000-8000-000000000001', 'b0000000-0000-4000-8000-000000000001', 'c0000000-0000-4000-8000-000000000002',
   extract(year FROM pg_temp.d(0))::int, extract(month FROM pg_temp.d(0))::int, 5000);
