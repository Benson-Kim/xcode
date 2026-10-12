-- Reverse of 0003_tenancy.sql.

SET LOCAL lock_timeout = '10s';

DROP TABLE tenancy.audit_events;
DROP TABLE tenancy.change_log;
DROP TABLE tenancy.user_preferences;
DROP TABLE tenancy.organization_security_policies;
DROP TABLE tenancy.organization_logos;
DROP TABLE tenancy.organization_brandings;
DROP TABLE tenancy.organization_localizations;
DROP TABLE tenancy.memberships;
DROP TABLE tenancy.organizations;
DROP FUNCTION tenancy.check_contrast(text, text);
DROP FUNCTION tenancy.current_request();
DROP FUNCTION tenancy.current_actor();
DROP FUNCTION tenancy.current_organization();
