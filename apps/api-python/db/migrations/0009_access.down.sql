-- Reverse of 0009_access.sql. Overrides are rebuilt from what each person holds now, read through the old keys (the kept keys, a retired key when a source is held, the Owner key); rights no old key expresses and every back-dating limit are lost; the brand checks come back NOT VALID.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS tenancy.save_person(
  uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text, integer, date,
  bigint, timestamptz
);
DROP FUNCTION IF EXISTS api.people_create(
  uuid, uuid, text, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text,
  integer, date, timestamptz
);
DROP FUNCTION IF EXISTS api.people_update(
  uuid, uuid, text, uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric,
  text, integer, date, bigint, timestamptz
);
DROP FUNCTION IF EXISTS api.people_pin_reset(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.people_device_remove(uuid, uuid, text, uuid, uuid, timestamptz);
DROP FUNCTION IF EXISTS tenancy.earliest_writable(uuid, uuid, date);
DROP FUNCTION IF EXISTS tenancy.check_writable(date, timestamptz);
DROP FUNCTION IF EXISTS tenancy.back_limit_words(text, integer, date);
DROP FUNCTION IF EXISTS tenancy.person_sign_in(uuid, timestamptz);

CREATE TEMPORARY TABLE access_members ON COMMIT DROP AS
SELECT m.organization_id, m.user_id, r.name AS role_name
FROM tenancy.memberships AS m
LEFT JOIN tenancy.person_roles AS pr
  ON pr.organization_id = m.organization_id AND pr.user_id = m.user_id
LEFT JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id;

CREATE TEMPORARY TABLE access_held ON COMMIT DROP AS
WITH RECURSIVE
starting AS (
  SELECT m.organization_id, m.user_id, d.permission
  FROM access_members AS m
  JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(m.role_name)
  UNION
  SELECT o.organization_id, o.user_id, o.permission
  FROM tenancy.permission_overrides AS o
  WHERE o.granted
),
expanded (organization_id, user_id, permission) AS (
  SELECT starting.organization_id, starting.user_id, starting.permission FROM starting
  UNION
  SELECT expanded.organization_id, expanded.user_id, dep.needs
  FROM expanded
  JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
)
SELECT expanded.organization_id, expanded.user_id, expanded.permission FROM expanded
EXCEPT
SELECT o.organization_id, o.user_id, o.permission
FROM tenancy.permission_overrides AS o
WHERE NOT o.granted;

CREATE TEMPORARY TABLE access_old_keys (key text PRIMARY KEY) ON COMMIT DROP;
INSERT INTO access_old_keys (key)
SELECT p.key FROM tenancy.permissions AS p
WHERE NOT p.catalogue
   OR p.key IN (
     'dash.net', 'dash.gaps', 'dash.pettycash', 'revenue.view', 'revenue.capture',
     'revenue.correct', 'expenses.view', 'expenses.capture', 'expenses.correct',
     'pettycash.spend', 'pettycash.view_all', 'pettycash.approve_item', 'pettycash.approve_day',
     'pettycash.issue', 'pettycash.issue_negative', 'reports.view', 'reports.export',
     'people.view', 'audit.view'
   );

CREATE TEMPORARY TABLE access_back_sets ON COMMIT DROP AS
SELECT h.organization_id, h.user_id, h.permission
FROM access_held AS h
JOIN access_old_keys AS k ON k.key = h.permission
UNION
SELECT DISTINCT h.organization_id, h.user_id, s.permission
FROM access_held AS h
JOIN tenancy.permission_sources AS s ON s.source = h.permission;

DROP TABLE tenancy.permission_translations;
DROP TABLE tenancy.permission_sources;
DELETE FROM tenancy.permission_overrides;
DELETE FROM tenancy.permission_dependencies;
DELETE FROM tenancy.role_defaults;
DELETE FROM tenancy.permissions AS p WHERE NOT EXISTS (SELECT 1 FROM access_old_keys AS k WHERE k.key = p.key);
ALTER TABLE tenancy.permissions
  DROP CONSTRAINT ck_permissions_section,
  DROP COLUMN section,
  DROP COLUMN catalogue;
UPDATE tenancy.permissions SET group_order = group_order + 100;

INSERT INTO tenancy.permissions (key, group_name, label, group_order, item_order) VALUES
  ('dash.capture', 'Dashboard', 'See today''s capture for my vehicles', 1, 1),
  ('dash.float', 'Dashboard', 'See my petty cash float', 1, 2),
  ('dash.revenue', 'Dashboard', 'See revenue totals', 1, 3),
  ('dash.net', 'Dashboard', 'See net contribution and weakest vehicles', 1, 4),
  ('dash.costs', 'Dashboard', 'See cost totals', 1, 5),
  ('dash.gaps', 'Dashboard', 'See missing revenue days', 1, 6),
  ('dash.pettycash', 'Dashboard', 'See petty cash waiting for approval', 1, 7),
  ('dash.commitments', 'Dashboard', 'See renewals due', 1, 8),
  ('dash.investment', 'Dashboard', 'See money invested and how much is back', 1, 9),
  ('dash.edits', 'Dashboard', 'See records edited after capture', 1, 10),
  ('revenue.view', 'Revenue', 'View revenue records', 2, 1),
  ('revenue.capture', 'Revenue', 'Capture revenue', 2, 2),
  ('revenue.no_earnings', 'Revenue', 'Record a no earnings reason', 2, 3),
  ('revenue.correct', 'Revenue', 'Correct revenue after the day', 2, 4),
  ('expenses.view', 'Expenses', 'View expenses', 3, 1),
  ('expenses.capture', 'Expenses', 'Record an expense straight onto a vehicle', 3, 2),
  ('expenses.correct', 'Expenses', 'Change an expense after the day', 3, 3),
  ('expenses.setup', 'Expenses', 'Set up expense categories and items', 3, 4),
  ('pettycash.spend', 'Petty cash', 'Record spending from my float', 4, 1),
  ('pettycash.view_all', 'Petty cash', 'View every float', 4, 2),
  ('pettycash.approve_item', 'Petty cash', 'Approve single entries', 4, 3),
  ('pettycash.approve_day', 'Petty cash', 'Approve a whole day', 4, 4),
  ('pettycash.issue', 'Petty cash', 'Record money sent to a float', 4, 5),
  ('pettycash.issue_negative', 'Petty cash', 'Send money that takes a float below zero', 4, 6),
  ('bills.view', 'Office bills', 'View office bills', 5, 1),
  ('bills.capture', 'Office bills', 'Capture office bills', 5, 2),
  ('bills.approve', 'Office bills', 'Approve office bills', 5, 3),
  ('commitments.view', 'Scheduled expenses and savings', 'View scheduled expenses and savings', 6, 1),
  ('commitments.manage', 'Scheduled expenses and savings',
    'Set up, change and stop scheduled expenses and savings', 6, 2),
  ('reports.view', 'Reports', 'View reports', 7, 1),
  ('reports.export', 'Reports', 'Export reports', 7, 2),
  ('companies.manage', 'Setup', 'Set up PSV companies', 8, 1),
  ('vehicles.manage', 'Setup', 'Set up vehicles and weekly targets', 8, 2),
  ('invest.view', 'Setup', 'See what was invested in a vehicle', 8, 3),
  ('invest.manage', 'Setup', 'Record what was invested in a vehicle', 8, 4),
  ('people.view', 'Setup', 'View people', 8, 5),
  ('people.manage', 'Setup', 'Add people, choose their role and what they can see, remove access', 8, 6),
  ('access.manage', 'Setup', 'Change single permissions and approval limits for a person', 8, 7),
  ('audit.view', 'Setup', 'View the change log', 8, 8),
  ('organization.manage', 'Setup', 'Manage organization settings', 8, 9)
ON CONFLICT (key) DO UPDATE
SET group_name = EXCLUDED.group_name,
    label = EXCLUDED.label,
    group_order = EXCLUDED.group_order,
    item_order = EXCLUDED.item_order;

INSERT INTO tenancy.permission_dependencies (permission, needs) VALUES
  ('dash.capture', 'revenue.capture'),
  ('dash.float', 'pettycash.spend'),
  ('dash.revenue', 'revenue.view'),
  ('dash.net', 'revenue.view'),
  ('dash.net', 'expenses.view'),
  ('dash.net', 'commitments.view'),
  ('dash.costs', 'expenses.view'),
  ('dash.costs', 'commitments.view'),
  ('dash.gaps', 'revenue.view'),
  ('dash.pettycash', 'pettycash.view_all'),
  ('dash.commitments', 'commitments.view'),
  ('dash.investment', 'invest.view'),
  ('dash.edits', 'audit.view'),
  ('revenue.capture', 'revenue.view'),
  ('revenue.no_earnings', 'revenue.capture'),
  ('revenue.correct', 'revenue.view'),
  ('expenses.capture', 'expenses.view'),
  ('expenses.correct', 'expenses.view'),
  ('expenses.setup', 'expenses.view'),
  ('pettycash.approve_item', 'pettycash.view_all'),
  ('pettycash.approve_day', 'pettycash.approve_item'),
  ('pettycash.issue', 'pettycash.view_all'),
  ('pettycash.issue_negative', 'pettycash.issue'),
  ('bills.capture', 'bills.view'),
  ('bills.approve', 'bills.view'),
  ('commitments.manage', 'commitments.view'),
  ('reports.export', 'reports.view'),
  ('invest.manage', 'invest.view'),
  ('people.manage', 'people.view'),
  ('access.manage', 'people.manage');

INSERT INTO tenancy.role_defaults (role_name, permission)
SELECT 'Owner', key FROM tenancy.permissions WHERE key <> 'dash.capture';

INSERT INTO tenancy.role_defaults (role_name, permission) VALUES
  ('Office admin', 'dash.revenue'),
  ('Office admin', 'dash.costs'),
  ('Office admin', 'dash.gaps'),
  ('Office admin', 'dash.commitments'),
  ('Office admin', 'dash.edits'),
  ('Office admin', 'revenue.view'),
  ('Office admin', 'revenue.correct'),
  ('Office admin', 'expenses.view'),
  ('Office admin', 'expenses.capture'),
  ('Office admin', 'expenses.correct'),
  ('Office admin', 'expenses.setup'),
  ('Office admin', 'bills.view'),
  ('Office admin', 'bills.capture'),
  ('Office admin', 'commitments.view'),
  ('Office admin', 'commitments.manage'),
  ('Office admin', 'reports.view'),
  ('Office admin', 'reports.export'),
  ('Office admin', 'invest.view'),
  ('Office admin', 'invest.manage'),
  ('Office admin', 'companies.manage'),
  ('Office admin', 'vehicles.manage'),
  ('Office admin', 'people.view'),
  ('Office admin', 'people.manage'),
  ('Office admin', 'audit.view'),
  ('Fleet manager', 'dash.float'),
  ('Fleet manager', 'dash.revenue'),
  ('Fleet manager', 'dash.costs'),
  ('Fleet manager', 'dash.gaps'),
  ('Fleet manager', 'revenue.view'),
  ('Fleet manager', 'revenue.capture'),
  ('Fleet manager', 'revenue.no_earnings'),
  ('Fleet manager', 'revenue.correct'),
  ('Fleet manager', 'pettycash.spend'),
  ('Fleet manager', 'expenses.view'),
  ('Fleet manager', 'reports.view'),
  ('Revenue clerk', 'dash.capture'),
  ('Revenue clerk', 'dash.gaps'),
  ('Revenue clerk', 'revenue.view'),
  ('Revenue clerk', 'revenue.capture'),
  ('Revenue clerk', 'revenue.no_earnings');

CREATE TEMPORARY TABLE access_role_back ON COMMIT DROP AS
WITH RECURSIVE expanded (organization_id, user_id, permission) AS (
  SELECT m.organization_id, m.user_id, d.permission
  FROM access_members AS m
  JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(m.role_name)
  UNION
  SELECT expanded.organization_id, expanded.user_id, dep.needs
  FROM expanded
  JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
)
SELECT * FROM expanded;

INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted)
SELECT b.organization_id, b.user_id, b.permission, true
FROM access_back_sets AS b
WHERE NOT EXISTS (
  SELECT 1 FROM access_role_back AS d
  WHERE d.organization_id = b.organization_id AND d.user_id = b.user_id AND d.permission = b.permission
)
UNION ALL
SELECT d.organization_id, d.user_id, d.permission, false
FROM access_role_back AS d
WHERE NOT EXISTS (
  SELECT 1 FROM access_back_sets AS b
  WHERE b.organization_id = d.organization_id AND b.user_id = d.user_id AND b.permission = d.permission
);

ALTER TABLE tenancy.memberships
  DROP CONSTRAINT ck_memberships_back_limit_count,
  DROP CONSTRAINT ck_memberships_back_limit_mode,
  DROP COLUMN back_limit_from,
  DROP COLUMN back_limit_count,
  DROP COLUMN back_limit_mode;

ALTER TABLE tenancy.organization_brandings
  DROP CONSTRAINT ck_brandings_domain,
  DROP CONSTRAINT ck_brandings_logo_light_url,
  DROP CONSTRAINT ck_brandings_logo_dark_url,
  DROP CONSTRAINT ck_brandings_favicon_url,
  DROP CONSTRAINT ck_brandings_terms_url,
  DROP CONSTRAINT ck_brandings_privacy_url,
  ADD CONSTRAINT ck_brandings_domain CHECK (
    char_length(domain) <= 253
    AND domain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
  ) NOT VALID,
  ADD CONSTRAINT ck_brandings_logo_light_url CHECK (
    logo_light_url ~ '^https://' AND char_length(logo_light_url) <= 2048
  ) NOT VALID,
  ADD CONSTRAINT ck_brandings_logo_dark_url CHECK (
    logo_dark_url ~ '^https://' AND char_length(logo_dark_url) <= 2048
  ) NOT VALID,
  ADD CONSTRAINT ck_brandings_favicon_url CHECK (
    favicon_url ~ '^https://' AND char_length(favicon_url) <= 2048
  ) NOT VALID,
  ADD CONSTRAINT ck_brandings_terms_url CHECK (
    terms_url ~ '^https://' AND char_length(terms_url) <= 2048
  ) NOT VALID,
  ADD CONSTRAINT ck_brandings_privacy_url CHECK (
    privacy_url ~ '^https://' AND char_length(privacy_url) <= 2048
  ) NOT VALID;
