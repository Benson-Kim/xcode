-- Access of the design notes v2.32 and v2.33: the 59-right catalogue with derived legacy keys and the hidden Owner key, the grant translation of every membership, the back-dating limit on the membership, and brand host and URL rules as wide as .NET's.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS tenancy.save_person(
  uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, bigint, timestamptz
);
DROP FUNCTION IF EXISTS api.people_create(
  uuid, uuid, text, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, timestamptz
);
DROP FUNCTION IF EXISTS api.people_update(
  uuid, uuid, text, uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric,
  bigint, timestamptz
);

-- How far back a person may change records: none, a number of days or months, and an
-- optional fixed date. Existing people keep "any date"; the person save gives new people 7 days.
ALTER TABLE tenancy.memberships
  ADD COLUMN back_limit_mode text NOT NULL DEFAULT 'none',
  ADD COLUMN back_limit_count smallint,
  ADD COLUMN back_limit_from date,
  ADD CONSTRAINT ck_memberships_back_limit_mode CHECK (back_limit_mode IN ('none', 'days', 'months')),
  ADD CONSTRAINT ck_memberships_back_limit_count CHECK (
    (back_limit_mode = 'none') = (back_limit_count IS NULL)
    AND (back_limit_mode <> 'days' OR back_limit_count BETWEEN 0 AND 3650)
    AND (back_limit_mode <> 'months' OR back_limit_count BETWEEN 0 AND 120)
  );

-- Brand host names and URLs as .NET accepts them (Uri.CheckHostName == Dns, an absolute https
-- URI): upper case, underscores, non-ASCII letters, one label and a trailing dot; the scheme in
-- any letter case. Every stored row met the narrower rules, so it meets these.
ALTER TABLE tenancy.organization_brandings
  DROP CONSTRAINT ck_brandings_domain,
  DROP CONSTRAINT ck_brandings_logo_light_url,
  DROP CONSTRAINT ck_brandings_logo_dark_url,
  DROP CONSTRAINT ck_brandings_favicon_url,
  DROP CONSTRAINT ck_brandings_terms_url,
  DROP CONSTRAINT ck_brandings_privacy_url,
  ADD CONSTRAINT ck_brandings_domain CHECK (
    char_length(domain) <= 253
    AND domain ~ '^[A-Za-z0-9_\u00a1-\uffff][A-Za-z0-9_\u00a1-\uffff-]*(\.[A-Za-z0-9_\u00a1-\uffff][A-Za-z0-9_\u00a1-\uffff-]*)*\.?$'
  ),
  ADD CONSTRAINT ck_brandings_logo_light_url CHECK (
    logo_light_url ~* '^https://' AND char_length(logo_light_url) <= 2048
  ),
  ADD CONSTRAINT ck_brandings_logo_dark_url CHECK (
    logo_dark_url ~* '^https://' AND char_length(logo_dark_url) <= 2048
  ),
  ADD CONSTRAINT ck_brandings_favicon_url CHECK (
    favicon_url ~* '^https://' AND char_length(favicon_url) <= 2048
  ),
  ADD CONSTRAINT ck_brandings_terms_url CHECK (
    terms_url ~* '^https://' AND char_length(terms_url) <= 2048
  ),
  ADD CONSTRAINT ck_brandings_privacy_url CHECK (
    privacy_url ~* '^https://' AND char_length(privacy_url) <= 2048
  );

CREATE TEMPORARY TABLE access_members ON COMMIT DROP AS
SELECT m.organization_id, m.user_id, r.name AS role_name
FROM tenancy.memberships AS m
LEFT JOIN tenancy.person_roles AS pr
  ON pr.organization_id = m.organization_id AND pr.user_id = m.user_id
LEFT JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id;

-- What every person holds under the old catalogue, read before it changes with the resolver
-- tenancy.assigned_permissions used (role defaults plus granted overrides, dependencies
-- expanded, denied overrides removed, keys whose needs are missing dropped).
CREATE TEMPORARY TABLE access_old_sets ON COMMIT DROP AS
WITH RECURSIVE
starting AS (
  SELECT m.organization_id, m.user_id, d.permission
  FROM tenancy.memberships AS m
  JOIN tenancy.person_roles AS pr
    ON pr.organization_id = m.organization_id AND pr.user_id = m.user_id
  JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id
  JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(r.name)
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
),
held AS (
  SELECT expanded.organization_id, expanded.user_id, expanded.permission FROM expanded
  EXCEPT
  SELECT o.organization_id, o.user_id, o.permission
  FROM tenancy.permission_overrides AS o
  WHERE NOT o.granted
),
closure (organization_id, user_id, root, permission) AS (
  SELECT held.organization_id, held.user_id, held.permission, held.permission FROM held
  UNION
  SELECT closure.organization_id, closure.user_id, closure.root, dep.needs
  FROM closure
  JOIN tenancy.permission_dependencies AS dep ON dep.permission = closure.permission
)
SELECT held.organization_id, held.user_id, held.permission
FROM held
WHERE NOT EXISTS (
  SELECT 1
  FROM closure
  WHERE closure.organization_id = held.organization_id
    AND closure.user_id = held.user_id
    AND closure.root = held.permission
    AND NOT EXISTS (
      SELECT 1
      FROM held AS again
      WHERE again.organization_id = closure.organization_id
        AND again.user_id = closure.user_id
        AND again.permission = closure.permission
    )
);

ALTER TABLE tenancy.permissions
  ADD COLUMN catalogue boolean NOT NULL DEFAULT true,
  ADD COLUMN section text,
  ADD CONSTRAINT ck_permissions_section CHECK (section IN ('View', 'Expenses', 'Approval', 'Cash'));

-- Out of the way of the new order first: the order index is checked row by row.
UPDATE tenancy.permissions SET group_order = group_order + 100;

INSERT INTO tenancy.permissions (
  key, group_name, label, group_order, item_order, catalogue, section
) VALUES
  ('dash.net', 'Dashboard', 'See revenue, money out and net', 1, 1, true, NULL),
  ('dash.gaps', 'Dashboard', 'See capture gaps', 1, 2, true, NULL),
  ('dash.pettycash', 'Dashboard', 'See petty cash position', 1, 3, true, NULL),
  ('revenue.view', 'Revenue', 'View revenue', 2, 1, true, NULL),
  ('revenue.capture', 'Revenue', 'Capture revenue', 2, 2, true, NULL),
  ('revenue.correct', 'Revenue', 'Change revenue already saved', 2, 3, true, NULL),
  ('revenue.export', 'Revenue', 'Export revenue', 2, 4, true, NULL),
  ('expenses.view', 'Central expenses', 'View central expenses', 3, 1, true, NULL),
  ('expenses.capture', 'Central expenses', 'Record an expense', 3, 2, true, NULL),
  ('expenses.correct', 'Central expenses', 'Edit an expense', 3, 3, true, NULL),
  ('expenses.export', 'Central expenses', 'Export central expenses', 3, 4, true, NULL),
  ('pettycash.view', 'Petty cash', 'View petty cash', 4, 1, true, 'View'),
  ('pettycash.view_all', 'Petty cash', 'See every manager''s float', 4, 2, true, 'View'),
  ('pettycash.reports', 'Petty cash', 'View petty cash reports', 4, 3, true, 'View'),
  ('pettycash.export', 'Petty cash', 'Export petty cash', 4, 4, true, 'View'),
  ('pettycash.spend', 'Petty cash', 'Add an expense', 4, 5, true, 'Expenses'),
  ('pettycash.spend_other', 'Petty cash', 'Add for another manager', 4, 6, true, 'Expenses'),
  ('pettycash.edit_own', 'Petty cash', 'Edit own expense', 4, 7, true, 'Expenses'),
  ('pettycash.edit', 'Petty cash', 'Edit any expense', 4, 8, true, 'Expenses'),
  ('pettycash.delete_own', 'Petty cash', 'Delete own expense', 4, 9, true, 'Expenses'),
  ('pettycash.delete', 'Petty cash', 'Delete any expense', 4, 10, true, 'Expenses'),
  ('pettycash.delete_approved', 'Petty cash', 'Delete after approval', 4, 11, true, 'Expenses'),
  ('pettycash.send_back', 'Petty cash', 'Send an expense back', 4, 12, true, 'Approval'),
  ('pettycash.approve_item', 'Petty cash', 'Approve an expense', 4, 13, true, 'Approval'),
  ('pettycash.approve_day', 'Petty cash', 'Approve a whole day', 4, 14, true, 'Approval'),
  ('pettycash.reject', 'Petty cash', 'Reject an expense', 4, 15, true, 'Approval'),
  ('pettycash.reopen', 'Petty cash', 'Reopen an approved or rejected expense', 4, 16, true, 'Approval'),
  ('pettycash.issue', 'Petty cash', 'Issue cash', 4, 17, true, 'Cash'),
  ('pettycash.issue_negative', 'Petty cash', 'Issue cash to a float below zero', 4, 18, true, 'Cash'),
  ('pettycash.credit', 'Petty cash', 'Record a credit note', 4, 19, true, 'Cash'),
  ('pettycash.delete_cash', 'Petty cash', 'Delete a cash entry', 4, 20, true, 'Cash'),
  ('scheduled.view', 'Scheduled expenses', 'View scheduled expenses', 5, 1, true, NULL),
  ('scheduled.add', 'Scheduled expenses', 'Add a scheduled expense', 5, 2, true, NULL),
  ('scheduled.edit', 'Scheduled expenses', 'Edit a scheduled expense', 5, 3, true, NULL),
  ('scheduled.pause', 'Scheduled expenses', 'Pause or resume', 5, 4, true, NULL),
  ('savings.view', 'Savings', 'View savings', 6, 1, true, NULL),
  ('savings.add', 'Savings', 'Add a saving', 6, 2, true, NULL),
  ('savings.edit', 'Savings', 'Edit a saving', 6, 3, true, NULL),
  ('savings.pause', 'Savings', 'Pause or resume', 6, 4, true, NULL),
  ('reports.view', 'Reports', 'View reports', 7, 1, true, NULL),
  ('reports.investment', 'Reports', 'See the investment report', 7, 2, true, NULL),
  ('reports.export', 'Reports', 'Export reports', 7, 3, true, NULL),
  ('companies.view', 'PSV companies', 'View companies', 8, 1, true, NULL),
  ('companies.add', 'PSV companies', 'Add a company', 8, 2, true, NULL),
  ('companies.edit', 'PSV companies', 'Edit a company', 8, 3, true, NULL),
  ('vehicles.view', 'Vehicles', 'View vehicles', 9, 1, true, NULL),
  ('vehicles.add', 'Vehicles', 'Add a vehicle', 9, 2, true, NULL),
  ('vehicles.edit', 'Vehicles', 'Edit a vehicle', 9, 3, true, NULL),
  ('vehicles.target', 'Vehicles', 'Set targets', 9, 4, true, NULL),
  ('catalog.view', 'Expense items', 'View items and categories', 10, 1, true, NULL),
  ('catalog.add', 'Expense items', 'Add an item or category', 10, 2, true, NULL),
  ('catalog.edit', 'Expense items', 'Edit an item or category', 10, 3, true, NULL),
  ('catalog.stop', 'Expense items', 'Stop or resume an item', 10, 4, true, NULL),
  ('people.view', 'People and access', 'View people', 11, 1, true, NULL),
  ('people.add', 'People and access', 'Add a person', 11, 2, true, NULL),
  ('people.edit', 'People and access', 'Edit a person and their access', 11, 3, true, NULL),
  ('people.block', 'People and access', 'Block or unblock a person', 11, 4, true, NULL),
  ('people.sign_in', 'People and access', 'Reset a PIN and remove devices', 11, 5, true, NULL),
  ('audit.view', 'Change log', 'View the change log', 12, 1, true, NULL),
  -- Keys v2.11 phones still read: held when a source is held (tenancy.permission_sources),
  -- never granted; and the Owner-only key of the organization settings.
  ('dash.capture', 'Dashboard', 'See today''s capture for my vehicles', 99, 1, false, NULL),
  ('dash.float', 'Dashboard', 'See my petty cash float', 99, 2, false, NULL),
  ('dash.revenue', 'Dashboard', 'See revenue totals', 99, 3, false, NULL),
  ('dash.costs', 'Dashboard', 'See cost totals', 99, 4, false, NULL),
  ('dash.commitments', 'Dashboard', 'See renewals due', 99, 5, false, NULL),
  ('dash.investment', 'Dashboard', 'See money invested and how much is back', 99, 6, false, NULL),
  ('dash.edits', 'Dashboard', 'See records edited after capture', 99, 7, false, NULL),
  ('revenue.no_earnings', 'Revenue', 'Record a no earnings reason', 99, 8, false, NULL),
  ('expenses.setup', 'Expenses', 'Set up expense categories and items', 99, 9, false, NULL),
  ('bills.view', 'Office bills', 'View office bills', 99, 10, false, NULL),
  ('bills.capture', 'Office bills', 'Capture office bills', 99, 11, false, NULL),
  ('bills.approve', 'Office bills', 'Approve office bills', 99, 12, false, NULL),
  ('commitments.view', 'Scheduled expenses and savings', 'View scheduled expenses and savings', 99, 13, false, NULL),
  ('commitments.manage', 'Scheduled expenses and savings',
    'Set up, change and stop scheduled expenses and savings', 99, 14, false, NULL),
  ('companies.manage', 'Setup', 'Set up PSV companies', 99, 15, false, NULL),
  ('vehicles.manage', 'Setup', 'Set up vehicles and weekly targets', 99, 16, false, NULL),
  ('invest.view', 'Setup', 'See what was invested in a vehicle', 99, 17, false, NULL),
  ('invest.manage', 'Setup', 'Record what was invested in a vehicle', 99, 18, false, NULL),
  ('people.manage', 'Setup', 'Add people, choose their role and what they can see, remove access', 99, 19, false, NULL),
  ('access.manage', 'Setup', 'Change single permissions and approval limits for a person', 99, 20, false, NULL),
  ('organization.manage', 'Setup', 'Manage organization settings', 99, 21, false, NULL)
ON CONFLICT (key) DO UPDATE
SET group_name = EXCLUDED.group_name,
    label = EXCLUDED.label,
    group_order = EXCLUDED.group_order,
    item_order = EXCLUDED.item_order,
    catalogue = EXCLUDED.catalogue,
    section = EXCLUDED.section;

DELETE FROM tenancy.permission_dependencies;
INSERT INTO tenancy.permission_dependencies (permission, needs) VALUES
  ('dash.net', 'revenue.view'),
  ('dash.gaps', 'revenue.view'),
  ('dash.pettycash', 'pettycash.view'),
  ('revenue.capture', 'revenue.view'),
  ('revenue.correct', 'revenue.view'),
  ('revenue.export', 'revenue.view'),
  ('expenses.capture', 'expenses.view'),
  ('expenses.correct', 'expenses.view'),
  ('expenses.export', 'expenses.view'),
  ('pettycash.view_all', 'pettycash.view'),
  ('pettycash.reports', 'pettycash.view'),
  ('pettycash.export', 'pettycash.view'),
  ('pettycash.spend', 'pettycash.view'),
  ('pettycash.spend_other', 'pettycash.view'),
  ('pettycash.edit_own', 'pettycash.view'),
  ('pettycash.edit', 'pettycash.view'),
  ('pettycash.delete_own', 'pettycash.view'),
  ('pettycash.delete', 'pettycash.view'),
  ('pettycash.delete_approved', 'pettycash.view'),
  ('pettycash.send_back', 'pettycash.view'),
  ('pettycash.approve_item', 'pettycash.view'),
  ('pettycash.approve_day', 'pettycash.approve_item'),
  ('pettycash.reject', 'pettycash.view'),
  ('pettycash.reopen', 'pettycash.view'),
  ('pettycash.issue', 'pettycash.view'),
  ('pettycash.issue_negative', 'pettycash.issue'),
  ('pettycash.credit', 'pettycash.view'),
  ('pettycash.delete_cash', 'pettycash.view'),
  ('scheduled.add', 'scheduled.view'),
  ('scheduled.edit', 'scheduled.view'),
  ('scheduled.pause', 'scheduled.view'),
  ('savings.add', 'savings.view'),
  ('savings.edit', 'savings.view'),
  ('savings.pause', 'savings.view'),
  ('reports.investment', 'reports.view'),
  ('reports.export', 'reports.view'),
  ('companies.add', 'companies.view'),
  ('companies.edit', 'companies.view'),
  ('vehicles.add', 'vehicles.view'),
  ('vehicles.edit', 'vehicles.view'),
  ('vehicles.target', 'vehicles.view'),
  ('catalog.add', 'catalog.view'),
  ('catalog.edit', 'catalog.view'),
  ('catalog.stop', 'catalog.view'),
  ('people.add', 'people.view'),
  ('people.edit', 'people.view'),
  ('people.block', 'people.view'),
  ('people.sign_in', 'people.view');

DELETE FROM tenancy.role_defaults;
INSERT INTO tenancy.role_defaults (role_name, permission)
SELECT 'Owner', p.key FROM tenancy.permissions AS p WHERE p.catalogue OR p.key = 'organization.manage';
INSERT INTO tenancy.role_defaults (role_name, permission) VALUES
  ('Office admin', 'dash.net'),
  ('Office admin', 'dash.gaps'),
  ('Office admin', 'revenue.view'),
  ('Office admin', 'revenue.correct'),
  ('Office admin', 'revenue.export'),
  ('Office admin', 'expenses.view'),
  ('Office admin', 'expenses.capture'),
  ('Office admin', 'expenses.correct'),
  ('Office admin', 'expenses.export'),
  ('Office admin', 'scheduled.view'),
  ('Office admin', 'scheduled.add'),
  ('Office admin', 'scheduled.edit'),
  ('Office admin', 'scheduled.pause'),
  ('Office admin', 'savings.view'),
  ('Office admin', 'savings.add'),
  ('Office admin', 'savings.edit'),
  ('Office admin', 'savings.pause'),
  ('Office admin', 'reports.view'),
  ('Office admin', 'reports.investment'),
  ('Office admin', 'reports.export'),
  ('Office admin', 'companies.view'),
  ('Office admin', 'companies.add'),
  ('Office admin', 'companies.edit'),
  ('Office admin', 'vehicles.view'),
  ('Office admin', 'vehicles.add'),
  ('Office admin', 'vehicles.edit'),
  ('Office admin', 'vehicles.target'),
  ('Office admin', 'catalog.view'),
  ('Office admin', 'catalog.add'),
  ('Office admin', 'catalog.edit'),
  ('Office admin', 'catalog.stop'),
  ('Office admin', 'people.view'),
  ('Office admin', 'people.add'),
  ('Office admin', 'people.edit'),
  ('Office admin', 'people.block'),
  ('Office admin', 'people.sign_in'),
  ('Office admin', 'audit.view'),
  ('Fleet manager', 'dash.net'),
  ('Fleet manager', 'dash.gaps'),
  ('Fleet manager', 'dash.pettycash'),
  ('Fleet manager', 'revenue.view'),
  ('Fleet manager', 'revenue.capture'),
  ('Fleet manager', 'revenue.correct'),
  ('Fleet manager', 'expenses.view'),
  ('Fleet manager', 'pettycash.view'),
  ('Fleet manager', 'pettycash.spend'),
  ('Fleet manager', 'pettycash.edit_own'),
  ('Fleet manager', 'reports.view'),
  ('Revenue clerk', 'dash.gaps'),
  ('Revenue clerk', 'revenue.view'),
  ('Revenue clerk', 'revenue.capture');

CREATE TABLE tenancy.permission_sources (
  permission text NOT NULL,
  source text NOT NULL,
  CONSTRAINT pk_permission_sources PRIMARY KEY (permission, source),
  CONSTRAINT fk_permission_sources_permission FOREIGN KEY (permission)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT fk_permission_sources_source FOREIGN KEY (source)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT ck_permission_sources_distinct CHECK (permission <> source)
);

INSERT INTO tenancy.permission_sources (permission, source) VALUES
  ('dash.capture', 'dash.gaps'),
  ('dash.float', 'dash.pettycash'),
  ('dash.revenue', 'dash.net'),
  ('dash.costs', 'dash.net'),
  ('dash.commitments', 'dash.net'),
  ('dash.investment', 'reports.investment'),
  ('dash.edits', 'dash.net'),
  ('revenue.no_earnings', 'revenue.capture'),
  ('revenue.no_earnings', 'revenue.correct'),
  ('expenses.setup', 'catalog.add'),
  ('expenses.setup', 'catalog.edit'),
  ('expenses.setup', 'catalog.stop'),
  ('commitments.view', 'scheduled.view'),
  ('commitments.view', 'savings.view'),
  ('commitments.manage', 'scheduled.add'),
  ('commitments.manage', 'scheduled.edit'),
  ('commitments.manage', 'scheduled.pause'),
  ('commitments.manage', 'savings.add'),
  ('commitments.manage', 'savings.edit'),
  ('commitments.manage', 'savings.pause'),
  ('companies.manage', 'companies.add'),
  ('companies.manage', 'companies.edit'),
  ('vehicles.manage', 'vehicles.add'),
  ('vehicles.manage', 'vehicles.edit'),
  ('vehicles.manage', 'vehicles.target'),
  ('invest.view', 'reports.investment'),
  ('invest.manage', 'vehicles.edit'),
  ('people.manage', 'people.add'),
  ('people.manage', 'people.edit'),
  ('people.manage', 'people.block'),
  ('people.manage', 'people.sign_in'),
  ('access.manage', 'people.edit');

CREATE TABLE tenancy.permission_translations (
  old_key text NOT NULL,
  new_key text NOT NULL,
  CONSTRAINT pk_permission_translations PRIMARY KEY (old_key, new_key),
  CONSTRAINT fk_permission_translations_old_key FOREIGN KEY (old_key)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT fk_permission_translations_new_key FOREIGN KEY (new_key)
    REFERENCES tenancy.permissions (key)
);

INSERT INTO tenancy.permission_translations (old_key, new_key) VALUES
  ('dash.capture', 'dash.gaps'),
  ('dash.float', 'dash.pettycash'),
  ('dash.pettycash', 'dash.pettycash'),
  ('dash.revenue', 'dash.net'),
  ('dash.net', 'dash.net'),
  ('dash.costs', 'dash.net'),
  ('dash.commitments', 'dash.net'),
  ('dash.edits', 'dash.net'),
  ('dash.gaps', 'dash.gaps'),
  ('dash.investment', 'reports.investment'),
  ('revenue.view', 'revenue.view'),
  ('revenue.capture', 'revenue.capture'),
  ('revenue.correct', 'revenue.correct'),
  ('expenses.view', 'expenses.view'),
  ('expenses.capture', 'expenses.capture'),
  ('expenses.correct', 'expenses.correct'),
  ('expenses.setup', 'catalog.view'),
  ('expenses.setup', 'catalog.add'),
  ('expenses.setup', 'catalog.edit'),
  ('expenses.setup', 'catalog.stop'),
  ('pettycash.spend', 'pettycash.spend'),
  ('pettycash.spend', 'pettycash.edit_own'),
  ('pettycash.view_all', 'pettycash.view_all'),
  ('pettycash.approve_item', 'pettycash.approve_item'),
  ('pettycash.approve_day', 'pettycash.approve_day'),
  ('pettycash.issue', 'pettycash.issue'),
  ('pettycash.issue_negative', 'pettycash.issue_negative'),
  ('commitments.view', 'scheduled.view'),
  ('commitments.view', 'savings.view'),
  ('commitments.manage', 'scheduled.add'),
  ('commitments.manage', 'scheduled.edit'),
  ('commitments.manage', 'scheduled.pause'),
  ('commitments.manage', 'savings.add'),
  ('commitments.manage', 'savings.edit'),
  ('commitments.manage', 'savings.pause'),
  ('reports.view', 'reports.view'),
  ('reports.export', 'reports.export'),
  ('reports.export', 'revenue.export'),
  ('reports.export', 'expenses.export'),
  ('reports.export', 'pettycash.export'),
  ('companies.manage', 'companies.view'),
  ('companies.manage', 'companies.add'),
  ('companies.manage', 'companies.edit'),
  ('vehicles.manage', 'vehicles.view'),
  ('vehicles.manage', 'vehicles.add'),
  ('vehicles.manage', 'vehicles.edit'),
  ('vehicles.manage', 'vehicles.target'),
  ('invest.view', 'reports.view'),
  ('invest.view', 'reports.investment'),
  ('invest.view', 'vehicles.view'),
  ('invest.manage', 'vehicles.edit'),
  ('people.view', 'people.view'),
  ('people.manage', 'people.add'),
  ('people.manage', 'people.edit'),
  ('people.manage', 'people.block'),
  ('people.manage', 'people.sign_in'),
  ('access.manage', 'people.edit'),
  ('audit.view', 'audit.view');

REVOKE ALL ON tenancy.permission_sources, tenancy.permission_translations FROM xcode_api_executor;
GRANT SELECT ON tenancy.permission_sources, tenancy.permission_translations
  TO xcode_api_executor, xcode_readonly;

-- Every person's new set: their old set translated key by key, the rights of their role no old
-- key leads to and nothing needs (the Owner's new petty-cash rights; everyone else's new rights
-- start off), and the base rights all of these need. The hidden Owner key comes from the role.
CREATE TEMPORARY TABLE access_new_sets ON COMMIT DROP AS
WITH RECURSIVE
chosen AS (
  SELECT o.organization_id, o.user_id, t.new_key AS permission
  FROM access_old_sets AS o
  JOIN tenancy.permission_translations AS t ON t.old_key = o.permission
  UNION
  SELECT members.organization_id, members.user_id, d.permission
  FROM access_members AS members
  JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(members.role_name)
  JOIN tenancy.permissions AS p ON p.key = d.permission AND p.catalogue
  WHERE NOT EXISTS (SELECT 1 FROM tenancy.permission_translations AS t WHERE t.new_key = d.permission)
    AND NOT EXISTS (SELECT 1 FROM tenancy.permission_dependencies AS dep WHERE dep.needs = d.permission)
),
expanded (organization_id, user_id, permission) AS (
  SELECT chosen.organization_id, chosen.user_id, chosen.permission FROM chosen
  UNION
  SELECT expanded.organization_id, expanded.user_id, dep.needs
  FROM expanded
  JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
)
SELECT expanded.organization_id, expanded.user_id, expanded.permission
FROM expanded
JOIN tenancy.permissions AS p ON p.key = expanded.permission AND p.catalogue;

CREATE TEMPORARY TABLE access_role_sets ON COMMIT DROP AS
SELECT m.organization_id, m.user_id, d.permission
FROM access_members AS m
JOIN tenancy.role_defaults AS d ON lower(d.role_name) = lower(m.role_name)
JOIN tenancy.permissions AS p ON p.key = d.permission AND p.catalogue;

DELETE FROM tenancy.permission_overrides;
INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted)
SELECT n.organization_id, n.user_id, n.permission, true
FROM access_new_sets AS n
WHERE NOT EXISTS (
  SELECT 1 FROM access_role_sets AS d
  WHERE d.organization_id = n.organization_id AND d.user_id = n.user_id AND d.permission = n.permission
)
UNION ALL
SELECT d.organization_id, d.user_id, d.permission, false
FROM access_role_sets AS d
WHERE NOT EXISTS (
  SELECT 1 FROM access_new_sets AS n
  WHERE n.organization_id = d.organization_id AND n.user_id = d.user_id AND n.permission = d.permission
);

DO $$
DECLARE
  v_members bigint;
  v_overrides bigint;
  v_grew bigint;
  v_dropped text;
BEGIN
  IF (SELECT count(*) FROM tenancy.permissions) <> 80
     OR (SELECT count(*) FROM tenancy.permissions WHERE catalogue) <> 59
     OR (SELECT count(*) FROM tenancy.permission_dependencies) <> 48
     OR (SELECT count(*) FROM tenancy.role_defaults) <> 111
     OR (SELECT count(*) FROM tenancy.permission_sources) <> 32
     OR (SELECT count(*) FROM tenancy.permission_translations) <> 58 THEN
    RAISE EXCEPTION 'permission catalogue rows are not 80 keys (59 in the catalogue), 48 dependencies, 111 role defaults, 32 sources, 58 translations';
  END IF;
  IF EXISTS (SELECT 1 FROM tenancy.permissions WHERE group_order > 99)
     OR EXISTS (
       SELECT 1 FROM tenancy.permission_sources AS s
       JOIN tenancy.permissions AS p ON p.key = s.source
       WHERE NOT p.catalogue
     )
     OR EXISTS (
       SELECT 1 FROM tenancy.permission_sources AS s
       JOIN tenancy.permissions AS p ON p.key = s.permission
       WHERE p.catalogue
     )
     OR EXISTS (
       SELECT 1 FROM tenancy.permissions AS p
       WHERE NOT p.catalogue
         AND p.key NOT IN ('organization.manage', 'bills.view', 'bills.capture', 'bills.approve')
         AND NOT EXISTS (SELECT 1 FROM tenancy.permission_sources AS s WHERE s.permission = p.key)
     )
     OR EXISTS (
       SELECT 1 FROM tenancy.permission_dependencies AS d
       JOIN tenancy.permissions AS p ON p.key IN (d.permission, d.needs)
       WHERE NOT p.catalogue
     )
     OR EXISTS (
       SELECT 1 FROM tenancy.role_defaults AS d
       JOIN tenancy.permissions AS p ON p.key = d.permission
       WHERE NOT p.catalogue AND (d.role_name <> 'Owner' OR d.permission <> 'organization.manage')
     )
     OR EXISTS (
       SELECT 1 FROM tenancy.permission_translations AS t
       JOIN tenancy.permissions AS p ON p.key = t.new_key
       WHERE NOT p.catalogue
     ) THEN
    RAISE EXCEPTION 'the catalogue, its sources, dependencies, role defaults or translations name the wrong keys';
  END IF;

  IF EXISTS (
    SELECT 1 FROM tenancy.permission_overrides AS o
    JOIN tenancy.permissions AS p ON p.key = o.permission
    WHERE NOT p.catalogue
  ) THEN
    RAISE EXCEPTION 'an override names a key outside the catalogue';
  END IF;

  -- The stored rows give every person exactly their new set.
  IF EXISTS (
    WITH stored AS (
      SELECT d.organization_id, d.user_id, d.permission
      FROM access_role_sets AS d
      WHERE NOT EXISTS (
        SELECT 1 FROM tenancy.permission_overrides AS o
        WHERE o.organization_id = d.organization_id AND o.user_id = d.user_id
          AND o.permission = d.permission AND NOT o.granted
      )
      UNION
      SELECT o.organization_id, o.user_id, o.permission
      FROM tenancy.permission_overrides AS o
      WHERE o.granted
    )
    (SELECT * FROM stored EXCEPT SELECT * FROM access_new_sets)
    UNION ALL
    (SELECT * FROM access_new_sets EXCEPT SELECT * FROM stored)
  ) THEN
    RAISE EXCEPTION 'the rewritten overrides do not reproduce the translated sets';
  END IF;

  -- Every old key a person held reaches the new set, except those dropped on purpose.
  IF EXISTS (
    SELECT 1
    FROM access_old_sets AS o
    WHERE o.permission NOT IN (
            'revenue.no_earnings', 'bills.view', 'bills.capture', 'bills.approve',
            'organization.manage'
          )
      AND (
        NOT EXISTS (SELECT 1 FROM tenancy.permission_translations AS t WHERE t.old_key = o.permission)
        OR EXISTS (
          SELECT 1
          FROM tenancy.permission_translations AS t
          WHERE t.old_key = o.permission
            AND NOT EXISTS (
              SELECT 1 FROM access_new_sets AS n
              WHERE n.organization_id = o.organization_id AND n.user_id = o.user_id
                AND n.permission = t.new_key
            )
        )
      )
  ) THEN
    RAISE EXCEPTION 'a person loses a right the translation keeps';
  END IF;

  SELECT count(*) INTO v_members FROM tenancy.memberships;
  SELECT count(*) INTO v_overrides FROM tenancy.permission_overrides;
  SELECT count(*) INTO v_grew
  FROM (
    SELECT n.organization_id, n.user_id
    FROM access_new_sets AS n
    WHERE NOT EXISTS (
      SELECT 1 FROM access_old_sets AS o
      JOIN tenancy.permission_translations AS t ON t.old_key = o.permission
      WHERE o.organization_id = n.organization_id AND o.user_id = n.user_id AND t.new_key = n.permission
    )
    GROUP BY n.organization_id, n.user_id
  ) AS grew;
  SELECT string_agg(dropped.permission || ' x' || dropped.people, ', ' ORDER BY dropped.permission)
  INTO v_dropped
  FROM (
    SELECT o.permission, count(*) AS people
    FROM access_old_sets AS o
    JOIN access_members AS m ON m.organization_id = o.organization_id AND m.user_id = o.user_id
    WHERE o.permission IN ('revenue.no_earnings', 'bills.view', 'bills.capture', 'bills.approve')
       OR (o.permission = 'organization.manage' AND lower(coalesce(m.role_name, '')) <> 'owner')
    GROUP BY o.permission
  ) AS dropped;
  RAISE NOTICE 'tenancy.permission_overrides: % members rewritten into % override rows; % gained a right through their role or a base right; dropped on purpose: %',
    v_members, v_overrides, v_grew, coalesce(v_dropped, 'none');
END
$$;
