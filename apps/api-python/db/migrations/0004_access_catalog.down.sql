-- Reverse of 0004_access_catalog.sql.

SET LOCAL lock_timeout = '10s';

REVOKE USAGE ON SCHEMA tenancy FROM xcode_readonly;
DROP TABLE tenancy.data_scope_vehicles;
DROP TABLE tenancy.data_scope_companies;
DROP TABLE tenancy.data_scopes;
DROP TABLE tenancy.permission_overrides;
DROP TABLE tenancy.person_roles;
DROP TABLE tenancy.roles;
DROP TABLE tenancy.role_defaults;
DROP TABLE tenancy.permission_dependencies;
DROP TABLE tenancy.permissions;
