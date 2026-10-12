-- tenancy.redact_person_snapshot(p_snapshot text, p_company_ids uuid[], p_vehicle_ids uuid[]) RETURNS text
-- Purpose: a people snapshot as a scoped viewer may read it: CompanyIds and VehicleIds keep only the ids inside the viewer's reach; every other key, the key order and the "null" of a creation stay as stored.
-- Callers: api.history_list.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_history_routines.py.

CREATE OR REPLACE FUNCTION tenancy.redact_person_snapshot(
  p_snapshot text,
  p_company_ids uuid[],
  p_vehicle_ids uuid[]
)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_document json;
  v_companies text[] := coalesce(p_company_ids, '{}'::uuid[])::text[];
  v_vehicles text[] := coalesce(p_vehicle_ids, '{}'::uuid[])::text[];
BEGIN
  IF p_snapshot IS NULL THEN
    RETURN NULL;
  END IF;
  v_document := p_snapshot::json;
  IF json_typeof(v_document) <> 'object' THEN
    RETURN p_snapshot;
  END IF;
  RETURN tenancy.compact_json((
    SELECT json_object_agg(
             e.key,
             CASE
               WHEN e.key IN ('CompanyIds', 'VehicleIds') AND json_typeof(e.value) = 'array' THEN (
                 SELECT coalesce(json_agg(item.value ORDER BY item.ord), '[]'::json)
                 FROM json_array_elements(e.value) WITH ORDINALITY AS item (value, ord)
                 WHERE lower(item.value #>> '{}') = ANY (
                   CASE WHEN e.key = 'CompanyIds' THEN v_companies ELSE v_vehicles END
                 )
               )
               ELSE e.value
             END
             ORDER BY e.ord
           )
    FROM json_each(v_document) WITH ORDINALITY AS e (key, value, ord)
  ))::text;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.redact_person_snapshot(text, uuid[], uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.redact_person_snapshot(text, uuid[], uuid[]) TO xcode_api_executor;
