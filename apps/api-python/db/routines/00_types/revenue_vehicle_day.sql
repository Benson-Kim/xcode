-- revenue.vehicle_day (vehicle_id uuid, day date, active boolean, away boolean, target numeric, counted boolean, record_id uuid, amount numeric, reason smallint, reason_label text, note text, corrected_after_date boolean, version bigint)
-- Purpose: one vehicle on one day: whether it is in the fleet, the day target (that weekday's figure of the target set in force), whether the day counts towards the figures, and the day's record when there is one.
-- Callers: revenue.vehicle_days, revenue.cell, revenue.vehicle_week, and the revenue routines.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('revenue.vehicle_day') IS NULL THEN
    CREATE TYPE revenue.vehicle_day AS (
      vehicle_id uuid,
      day date,
      active boolean,
      away boolean,
      target numeric,
      counted boolean,
      record_id uuid,
      amount numeric,
      reason smallint,
      reason_label text,
      note text,
      corrected_after_date boolean,
      version bigint
    );
  END IF;
END
$$;
