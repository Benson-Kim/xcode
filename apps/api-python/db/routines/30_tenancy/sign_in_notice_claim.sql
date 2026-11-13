-- api.sign_in_notice_claim(p_now timestamptz, p_limit integer, p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid) RETURNS jsonb
-- Purpose: claim (FOR UPDATE SKIP LOCKED) up to p_limit pending sign-in notices for a send, oldest first. Right after a change (the actor, organization and request of the change, which enter the organization with people.edit, and p_user_id): that person's notices in that organization never yet attempted, none without p_user_id. The sweep (all four NULL): entering each organization in turn (tenancy.organization_ids, oldest first, so row-level security holds), the notices whose last attempt is over 5 minutes old. One at tenancy.sign_in_notice_sends() attempts becomes failed; one for an erased account, or a 'new' or 'current' one whose address is no longer the account's email, becomes dropped; both lose their address. Each of the rest gets a counted attempt and an element of the returned array (notice_id, organization_id, address, kind, first_name, actor_name (NULL when the actor is gone), organization_name, and new_address_hint: for an 'old' notice the account's email now through identity.mask_email, otherwise NULL); '[]' when there is nothing to send.
-- Callers: TenancyRoutines.claim_sign_in_notices; SignInNotices (after api.people_update commits, and the sign-in notice sweep).
-- Reads: tenancy.sign_in_notices, tenancy.memberships, tenancy.organizations, identity.users, and what tenancy.enter_organization, tenancy.organization_ids and identity.mask_email read. Writes: tenancy.sign_in_notices (state, address, attempts, attempted_at).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization (right after a change only).
-- Tests: tests/db/test_sign_in_notices.py.

CREATE OR REPLACE FUNCTION api.sign_in_notice_claim(
  p_now timestamptz,
  p_limit integer,
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_limit integer := greatest(coalesce(p_limit, 0), 0);
  v_sweep boolean := p_actor_id IS NULL AND p_organization_id IS NULL AND p_request_id IS NULL
    AND p_user_id IS NULL;
  v_organizations uuid[];
  v_organization_id uuid;
  v_taken integer := 0;
  v_candidates integer;
  v_batch jsonb;
  v_claimed jsonb := '[]'::jsonb;
BEGIN
  IF NOT v_sweep THEN
    PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.edit');
  END IF;
  IF v_limit = 0 OR (NOT v_sweep AND p_user_id IS NULL) THEN
    RETURN v_claimed;
  END IF;
  v_organizations := CASE WHEN v_sweep THEN tenancy.organization_ids() ELSE ARRAY[p_organization_id] END;

  FOREACH v_organization_id IN ARRAY v_organizations LOOP
    EXIT WHEN v_taken >= v_limit;
    PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
    WITH candidates AS (
      SELECT n.id, n.created_at, n.user_id, n.kind, n.address, n.attempts
      FROM tenancy.sign_in_notices AS n
      WHERE n.organization_id = v_organization_id
        AND n.state = 'pending'
        AND CASE
              WHEN v_sweep THEN coalesce(n.attempted_at, n.created_at) < p_now - interval '5 minutes'
              ELSE n.user_id = p_user_id AND n.attempted_at IS NULL
            END
      ORDER BY n.created_at, n.id
      LIMIT v_limit - v_taken
      FOR UPDATE OF n SKIP LOCKED
    ),
    judged AS (
      SELECT
        c.id,
        CASE
          WHEN c.attempts >= tenancy.sign_in_notice_sends() THEN 'failed'
          WHEN u.erased_at IS NOT NULL
            OR (c.kind <> 'old' AND c.address IS DISTINCT FROM u.email) THEN 'dropped'
        END AS end_state
      FROM candidates AS c
      JOIN identity.users AS u ON u.id = c.user_id
    ),
    ended AS (
      UPDATE tenancy.sign_in_notices AS n
      SET state = j.end_state, address = NULL
      FROM judged AS j
      WHERE n.id = j.id AND j.end_state IS NOT NULL
      RETURNING n.id
    ),
    claimed AS (
      UPDATE tenancy.sign_in_notices AS n
      SET attempts = n.attempts + 1, attempted_at = p_now
      FROM judged AS j
      WHERE n.id = j.id AND j.end_state IS NULL
      RETURNING n.id, n.created_at, n.user_id, n.actor_id, n.kind, n.address
    )
    SELECT
      (SELECT count(*) FROM candidates)::integer,
      coalesce(
        jsonb_agg(
          jsonb_build_object(
            'notice_id', c.id,
            'organization_id', v_organization_id,
            'address', c.address,
            'kind', c.kind,
            'first_name', m.first_name,
            'actor_name', a.first_name || ' ' || a.last_name,
            'organization_name', o.name,
            'new_address_hint', CASE WHEN c.kind = 'old' THEN identity.mask_email(u.email) END
          )
          ORDER BY c.created_at, c.id),
        '[]'::jsonb)
    INTO v_candidates, v_batch
    FROM claimed AS c
    JOIN tenancy.memberships AS m
      ON m.organization_id = v_organization_id AND m.user_id = c.user_id
    JOIN identity.users AS u ON u.id = c.user_id
    LEFT JOIN tenancy.memberships AS a
      ON a.organization_id = v_organization_id AND a.user_id = c.actor_id
    JOIN tenancy.organizations AS o ON o.id = v_organization_id;
    v_taken := v_taken + v_candidates;
    v_claimed := v_claimed || v_batch;
  END LOOP;
  RETURN v_claimed;
END;
$$;
