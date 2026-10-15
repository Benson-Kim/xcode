-- setup.record_setup_change(p_section text, p_entity_id uuid, p_vehicle_id uuid, p_before json, p_after json, p_reason text, p_now timestamptz) RETURNS bigint
-- Purpose: log a setup change through tenancy.record_change with the setup audit shape: action setup.<section>, the entity id as the audited entity, the snapshots as the audited before and after; returns the new settings_version.
-- Callers: the setup write routines, once and last.
-- Reads: what tenancy.record_change reads. Writes: what tenancy.record_change writes.
-- Raises: XC403 not_member via tenancy.record_change.
-- Tests: tests/db/test_setup_company_routines.py.

CREATE OR REPLACE FUNCTION setup.record_setup_change(
  p_section text,
  p_entity_id uuid,
  p_vehicle_id uuid,
  p_before json,
  p_after json,
  p_reason text,
  p_now timestamptz
)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN tenancy.record_change(
    p_section, p_entity_id, p_vehicle_id, p_before, p_after, p_reason,
    'setup.' || p_section, p_entity_id::text, p_before::jsonb, p_after::jsonb, p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.record_setup_change(text, uuid, uuid, json, json, text, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.record_setup_change(text, uuid, uuid, json, json, text, timestamptz)
  TO xcode_api_executor;
