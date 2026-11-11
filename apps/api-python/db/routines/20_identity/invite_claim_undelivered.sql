-- api.invite_claim_undelivered(p_now timestamptz, p_limit integer, p_token_hashes text[], p_code_hashes text[]) RETURNS jsonb
-- Purpose: the undelivered sweep: entering each organization in turn (tenancy.organization_ids, oldest first, so row-level security holds), claim (FOR UPDATE SKIP LOCKED) up to p_limit live pending invitations in all, never more than the hash pairs given, whose last attempt (or creation) is over 5 minutes old, oldest first within each organization; those past expires_at or at identity.invitation_sends() attempts become failed, and each of the rest gets the next pair of fresh digests (the raw link and code are never stored), a counted attempt and an element of the returned array: the identity.invitation_delivery fields plus pair_index, 0-based into the arrays; '[]' when there is nothing to send.
-- Callers: IdentityRoutines.invite_claim_undelivered; the undelivered invitation sweep.
-- Reads: identity.invitations, and what tenancy.organization_ids and identity.invitation_delivery read. Writes: identity.invitations (token_hash, code_hash, attempted_at, delivery_attempts, delivery_state).
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION api.invite_claim_undelivered(
  p_now timestamptz,
  p_limit integer,
  p_token_hashes text[],
  p_code_hashes text[]
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_limit integer := least(
    greatest(coalesce(p_limit, 0), 0),
    coalesce(cardinality(p_token_hashes), 0),
    coalesce(cardinality(p_code_hashes), 0)
  );
  v_organization_id uuid;
  v_taken integer := 0;
  v_paired integer := 0;
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
      SELECT
        i.id,
        i.created_at,
        i.delivery_attempts >= identity.invitation_sends() OR p_now > i.expires_at AS give_up
      FROM identity.invitations AS i
      WHERE i.organization_id = v_organization_id
        AND i.delivery_state = 'pending'
        AND i.accepted_at IS NULL AND i.revoked_at IS NULL
        AND coalesce(i.attempted_at, i.created_at) < p_now - interval '5 minutes'
      ORDER BY i.created_at, i.id
      LIMIT v_limit - v_taken
      FOR UPDATE SKIP LOCKED
    ),
    numbered AS (
      SELECT
        c.id,
        (v_paired + row_number() OVER (ORDER BY c.created_at, c.id) - 1)::integer AS pair_index
      FROM candidates AS c
      WHERE NOT c.give_up
    ),
    given_up AS (
      UPDATE identity.invitations AS i
      SET delivery_state = 'failed'
      FROM candidates AS c
      WHERE i.id = c.id AND c.give_up
      RETURNING i.id
    ),
    claimed AS (
      UPDATE identity.invitations AS i
      SET token_hash = p_token_hashes[n.pair_index + 1],
          code_hash = p_code_hashes[n.pair_index + 1],
          attempted_at = p_now,
          delivery_attempts = i.delivery_attempts + 1
      FROM numbered AS n
      WHERE i.id = n.id
      RETURNING n.pair_index, identity.invitation_delivery(i) AS delivery
    )
    SELECT
      (SELECT count(*) FROM candidates)::integer,
      coalesce(
        jsonb_agg(c.delivery || jsonb_build_object('pair_index', c.pair_index) ORDER BY c.pair_index),
        '[]'::jsonb
      )
    INTO v_candidates, v_batch
    FROM claimed AS c;
    v_taken := v_taken + v_candidates;
    v_paired := v_paired + jsonb_array_length(v_batch);
    v_claimed := v_claimed || v_batch;
  END LOOP;
  RETURN v_claimed;
END;
$$;
