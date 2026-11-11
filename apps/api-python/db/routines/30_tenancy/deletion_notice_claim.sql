-- api.deletion_notice_claim(p_now timestamptz, p_limit integer) RETURNS jsonb
-- Purpose: the deletion notice sweep: entering each organization in turn (tenancy.organization_ids, oldest first, so row-level security holds), claim (FOR UPDATE SKIP LOCKED) up to p_limit pending notices in all whose last attempt is over 5 minutes old, oldest first within each organization. One at tenancy.deletion_notice_sends() attempts becomes failed; one whose recipient no longer holds people.block on an active membership and account, or whose requester is no longer an active member, becomes dropped; each of the rest gets a counted attempt and an element of the returned array (notice_id, organization_id, email, first_name, requester_name, organization_name); '[]' when there is nothing to send.
-- Callers: TenancyRoutines.claim_deletion_notices; the deletion notice sweep.
-- Reads: tenancy.deletion_notices, tenancy.memberships, tenancy.organizations, identity.users, and what tenancy.organization_ids and tenancy.effective_permissions read. Writes: tenancy.deletion_notices (state, attempts, attempted_at).
-- Raises: none.
-- Tests: tests/db/test_deletion_routines.py.

CREATE OR REPLACE FUNCTION api.deletion_notice_claim(p_now timestamptz, p_limit integer)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_limit integer := greatest(coalesce(p_limit, 0), 0);
  v_organization_id uuid;
  v_taken integer := 0;
  v_candidates integer;
  v_batch jsonb;
  v_claimed jsonb := '[]'::jsonb;
BEGIN
  IF v_limit = 0 THEN
    RETURN v_claimed;
  END IF;

  FOREACH v_organization_id IN ARRAY tenancy.organization_ids() LOOP
    EXIT WHEN v_taken >= v_limit;
    PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
    WITH candidates AS (
      SELECT n.id, n.created_at, n.requester_id, n.recipient_id, n.attempts
      FROM tenancy.deletion_notices AS n
      WHERE n.organization_id = v_organization_id
        AND n.state = 'pending'
        AND coalesce(n.attempted_at, n.created_at) < p_now - interval '5 minutes'
      ORDER BY n.created_at, n.id
      LIMIT v_limit - v_taken
      FOR UPDATE SKIP LOCKED
    ),
    judged AS (
      SELECT
        c.id,
        c.created_at,
        CASE
          WHEN c.attempts >= tenancy.deletion_notice_sends() THEN 'failed'
          WHEN NOT EXISTS (
                 SELECT 1
                 FROM tenancy.memberships AS m
                 JOIN identity.users AS u ON u.id = m.user_id
                 WHERE m.organization_id = v_organization_id
                   AND m.user_id = c.recipient_id
                   AND m.active
                   AND u.status = 'active'
                   AND 'people.block' = ANY (
                     tenancy.effective_permissions(v_organization_id, c.recipient_id))
               )
            OR NOT EXISTS (
                 SELECT 1
                 FROM tenancy.memberships AS m
                 WHERE m.organization_id = v_organization_id
                   AND m.user_id = c.requester_id
                   AND m.active
               ) THEN 'dropped'
        END AS end_state
      FROM candidates AS c
    ),
    ended AS (
      UPDATE tenancy.deletion_notices AS n
      SET state = j.end_state
      FROM judged AS j
      WHERE n.id = j.id AND j.end_state IS NOT NULL
      RETURNING n.id
    ),
    claimed AS (
      UPDATE tenancy.deletion_notices AS n
      SET attempts = n.attempts + 1, attempted_at = p_now
      FROM judged AS j
      WHERE n.id = j.id AND j.end_state IS NULL
      RETURNING n.id, n.created_at, n.requester_id, n.recipient_id
    )
    SELECT
      (SELECT count(*) FROM candidates)::integer,
      coalesce(
        jsonb_agg(
          jsonb_build_object(
            'notice_id', c.id,
            'organization_id', v_organization_id,
            'email', u.email,
            'first_name', m.first_name,
            'requester_name', r.first_name || ' ' || r.last_name,
            'organization_name', o.name
          )
          ORDER BY c.created_at, c.id),
        '[]'::jsonb)
    INTO v_candidates, v_batch
    FROM claimed AS c
    JOIN tenancy.memberships AS m
      ON m.organization_id = v_organization_id AND m.user_id = c.recipient_id
    JOIN identity.users AS u ON u.id = c.recipient_id
    JOIN tenancy.memberships AS r
      ON r.organization_id = v_organization_id AND r.user_id = c.requester_id
    JOIN tenancy.organizations AS o ON o.id = v_organization_id;
    v_taken := v_taken + v_candidates;
    v_claimed := v_claimed || v_batch;
  END LOOP;
  RETURN v_claimed;
END;
$$;
