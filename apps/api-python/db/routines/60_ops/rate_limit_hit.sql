-- api.rate_limit_hit(p_key text, p_limit integer, p_window_seconds integer, p_now timestamptz)
--   RETURNS TABLE (allowed boolean, remaining integer, retry_after_seconds integer)
-- Purpose: charge one hit against a fixed window and return the decision; backs PostgresRateLimiter.
-- Callers: OpsRoutines.rate_limit_hit via PostgresRateLimiter.
-- Reads: ops.rate_limit_windows. Writes: ops.rate_limit_windows.
-- Raises: XC422 rate_limit_invalid (a limit or window below 1, or a key over 256 characters).
-- Tests: tests/db/test_ops_routines.py, tests/db/test_rate_limit_postgres.py.

CREATE OR REPLACE FUNCTION api.rate_limit_hit(
  p_key text,
  p_limit integer,
  p_window_seconds integer,
  p_now timestamptz
)
RETURNS TABLE (allowed boolean, remaining integer, retry_after_seconds integer)
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_window_start timestamptz;
  v_window_end timestamptz;
  v_count integer;
  v_retry integer;
BEGIN
  IF p_limit < 1 THEN
    PERFORM tenancy.refuse('rate_limit_invalid', 'XC422', '{"field": "limit"}');
  END IF;
  IF p_window_seconds < 1 THEN
    PERFORM tenancy.refuse('rate_limit_invalid', 'XC422', '{"field": "window_seconds"}');
  END IF;
  IF char_length(p_key) > 256 THEN
    PERFORM tenancy.refuse('rate_limit_invalid', 'XC422', '{"field": "key"}');
  END IF;

  v_window_start := to_timestamp(
    floor(extract(epoch FROM p_now) / p_window_seconds) * p_window_seconds
  );
  v_window_end := v_window_start + make_interval(secs => p_window_seconds);

  INSERT INTO ops.rate_limit_windows (key, window_start, count)
  VALUES (p_key, v_window_start, 1)
  ON CONFLICT (key, window_start)
  DO UPDATE SET count = ops.rate_limit_windows.count + 1
  RETURNING count INTO v_count;

  DELETE FROM ops.rate_limit_windows
  WHERE key = p_key
    AND window_start < v_window_start - make_interval(secs => 2 * p_window_seconds);

  v_retry := greatest(0, ceil(extract(epoch FROM (v_window_end - p_now)))::integer);

  IF v_count > p_limit THEN
    RETURN QUERY SELECT false, 0, v_retry;
  ELSE
    RETURN QUERY SELECT true, p_limit - v_count, v_retry;
  END IF;
END;
$$;
