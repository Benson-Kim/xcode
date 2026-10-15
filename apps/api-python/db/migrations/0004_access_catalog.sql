-- Access tables: roles, person_roles, permission_overrides, data_scopes, data_scope_companies, data_scope_vehicles; the permission catalogue with its rows.

SET LOCAL lock_timeout = '10s';

CREATE TABLE tenancy.permissions (
  key text NOT NULL,
  group_name text NOT NULL,
  label text NOT NULL,
  group_order smallint NOT NULL,
  item_order smallint NOT NULL,
  CONSTRAINT pk_permissions PRIMARY KEY (key),
  CONSTRAINT uq_permissions_order UNIQUE (group_order, item_order),
  CONSTRAINT ck_permissions_key CHECK (key ~ '^[a-z]+\.[a-z_]+$')
);

CREATE TABLE tenancy.permission_dependencies (
  permission text NOT NULL,
  needs text NOT NULL,
  CONSTRAINT pk_permission_dependencies PRIMARY KEY (permission, needs),
  CONSTRAINT fk_permission_dependencies_permission FOREIGN KEY (permission)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT fk_permission_dependencies_needs FOREIGN KEY (needs)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT ck_permission_dependencies_distinct CHECK (permission <> needs)
);

CREATE TABLE tenancy.role_defaults (
  role_name text NOT NULL,
  permission text NOT NULL,
  CONSTRAINT pk_role_defaults PRIMARY KEY (role_name, permission),
  CONSTRAINT fk_role_defaults_permission FOREIGN KEY (permission)
    REFERENCES tenancy.permissions (key),
  CONSTRAINT ck_role_defaults_role_name CHECK (
    role_name IN ('Owner', 'Office admin', 'Fleet manager', 'Revenue clerk')
  )
);

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
  ('organization.manage', 'Setup', 'Manage organization settings', 8, 9);

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

DO $$
BEGIN
  IF (SELECT count(*) FROM tenancy.permissions) <> 40
     OR (SELECT count(*) FROM tenancy.permission_dependencies) <> 30
     OR (SELECT count(*) FROM tenancy.role_defaults) <> 79 THEN
    RAISE EXCEPTION 'permission catalogue rows are not 40 keys, 30 dependencies, 79 role defaults';
  END IF;
END
$$;

CREATE TABLE tenancy.roles (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_roles PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_roles_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_roles_name CHECK (char_length(name) BETWEEN 1 AND 100)
);

CREATE UNIQUE INDEX uq_roles_name ON tenancy.roles (organization_id, lower(name));

CREATE TABLE tenancy.person_roles (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  role_id uuid NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_person_roles PRIMARY KEY (organization_id, user_id),
  CONSTRAINT fk_person_roles_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_person_roles_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_person_roles_role FOREIGN KEY (organization_id, role_id)
    REFERENCES tenancy.roles (organization_id, id)
);

CREATE TABLE tenancy.permission_overrides (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  permission text NOT NULL,
  granted boolean NOT NULL,
  CONSTRAINT pk_permission_overrides PRIMARY KEY (organization_id, user_id, permission),
  CONSTRAINT fk_permission_overrides_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_permission_overrides_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_permission_overrides_permission FOREIGN KEY (permission)
    REFERENCES tenancy.permissions (key)
);

CREATE TABLE tenancy.data_scopes (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  all_companies boolean NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_data_scopes PRIMARY KEY (organization_id, user_id),
  CONSTRAINT fk_data_scopes_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_data_scopes_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id)
);

-- The company and vehicle foreign keys are added with the setup tables they point at.
CREATE TABLE tenancy.data_scope_companies (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  company_id uuid NOT NULL,
  CONSTRAINT pk_data_scope_companies PRIMARY KEY (organization_id, user_id, company_id),
  CONSTRAINT fk_data_scope_companies_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_data_scope_companies_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id)
);

CREATE INDEX ix_data_scope_companies_company ON tenancy.data_scope_companies (organization_id, company_id);

CREATE TABLE tenancy.data_scope_vehicles (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  CONSTRAINT pk_data_scope_vehicles PRIMARY KEY (organization_id, user_id, vehicle_id),
  CONSTRAINT fk_data_scope_vehicles_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_data_scope_vehicles_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id)
);

CREATE INDEX ix_data_scope_vehicles_vehicle ON tenancy.data_scope_vehicles (organization_id, vehicle_id);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.person_roles
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.data_scopes
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE tenancy.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.person_roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.permission_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.data_scopes ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.data_scope_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.data_scope_vehicles ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenancy.roles TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.person_roles TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.permission_overrides TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.data_scopes TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.data_scope_companies TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.data_scope_vehicles TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.permissions, tenancy.permission_dependencies, tenancy.role_defaults,
  tenancy.roles, tenancy.person_roles, tenancy.permission_overrides, tenancy.data_scopes,
  tenancy.data_scope_companies, tenancy.data_scope_vehicles FROM xcode_api_executor;
GRANT SELECT ON tenancy.permissions, tenancy.permission_dependencies, tenancy.role_defaults
  TO xcode_api_executor, xcode_readonly;
GRANT USAGE ON SCHEMA tenancy TO xcode_readonly;
GRANT SELECT, INSERT ON tenancy.roles TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON tenancy.person_roles TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenancy.permission_overrides, tenancy.data_scopes
  TO xcode_api_executor;
GRANT SELECT, INSERT, DELETE ON tenancy.data_scope_companies, tenancy.data_scope_vehicles
  TO xcode_api_executor;
