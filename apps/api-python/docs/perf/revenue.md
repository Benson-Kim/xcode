# Revenue reads and capture at 10x

`EXPLAIN (ANALYZE, BUFFERS)` evidence for `api.revenue_week_get`, `api.revenue_dashboard_get`
and `api.revenue_capture` (`docs/03-database.md` section 9, `docs/05-routines.md` section 7),
measured on 2026-10-11.

## Seed

The demo seed (`api.ops_seed_demo`) does not exist yet. Prompt 09 builds it, and its
`seed_10x` helper replaces the script used here. The 10x seed used here has two organizations
(the second only adds rows that every index and policy has to skip), each with:

- 10 companies and 500 vehicles: ten times a demo fleet of 50.
- Join dates: 2025-09-01, except one vehicle in ten, which joins up to 200 days later. One in
  fifty left 30 days before the business date.
- Targets: a first weekly target from the join date (5,000 to 8,900); a third of the vehicles
  have a second one from 120 days back.
- Time away: one vehicle in ten has a 10-day away period 80 to 150 days back.
- Records: one for every day in the fleet through the business date, except 3% of days missing
  at random, the business date for 30% of the vehicles, and the days away. 5% are no-earnings
  reasons and 2% are corrections (version 2).

That gives about 13 months of history, not the demo's six weeks, because the earliest
missing day and the week's figures cost more as the history grows. Rows:

- 381,655 records in all, about 190,000 per organization;
- 1,002 vehicles, 1,307 target revisions and 111 away periods.

The seed runs as `xcode_owner` in a disposable clone of the test template, followed by
`VACUUM ANALYZE`:

```sql
INSERT INTO setup.psv_companies (organization_id, name)
SELECT %(org)s, 'Company ' || lpad(n::text, 2, '0') FROM generate_series(1, 10) AS n;

INSERT INTO setup.fleet_vehicles (organization_id, company_id, registration, joined_on, left_on)
SELECT %(org)s,
       (SELECT c.id FROM setup.psv_companies AS c WHERE c.organization_id = %(org)s
        ORDER BY c.name OFFSET (n % 10) LIMIT 1),
       'K' || chr(65 + n % 26) || chr(65 + (n / 26) % 26) || ' ' || lpad(n::text, 3, '0') || 'X',
       CASE WHEN n % 10 = 0 THEN %(start)s::date + (n % 200) ELSE %(start)s::date END,
       CASE WHEN n % 50 = 7 THEN %(today)s::date - 30 ELSE NULL END
FROM generate_series(1, 500) AS n;

INSERT INTO setup.vehicle_targets (organization_id, vehicle_id, revision, effective_from, weekly_amount)
SELECT f.organization_id, f.id, 1, f.joined_on, 5000 + (abs(hashtext(f.registration)) % 40) * 100
FROM setup.fleet_vehicles AS f WHERE f.organization_id = %(org)s AND f.registration LIKE '%X';

INSERT INTO setup.vehicle_targets (organization_id, vehicle_id, revision, effective_from, weekly_amount)
SELECT f.organization_id, f.id, 2, %(today)s::date - 120, 7000
FROM setup.fleet_vehicles AS f
WHERE f.organization_id = %(org)s AND f.registration LIKE '%X' AND abs(hashtext(f.registration)) % 3 = 0;

INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, returned_on)
SELECT f.organization_id, f.id, %(today)s::date - 90 - (abs(hashtext(f.registration)) % 60),
       %(today)s::date - 80 - (abs(hashtext(f.registration)) % 60)
FROM setup.fleet_vehicles AS f
WHERE f.organization_id = %(org)s AND f.registration LIKE '%X' AND abs(hashtext(f.registration)) % 10 = 1;

INSERT INTO revenue.records (organization_id, vehicle_id, business_date, amount, reason, note,
                             captured_at, captured_by, updated_at, updated_by,
                             corrected_after_date, version)
SELECT f.organization_id, f.id, d.day,
       CASE WHEN k.kind < 95 THEN 400 + (k.kind * 13 % 1100) END,
       CASE WHEN k.kind >= 95 THEN 1 + (k.kind % 3) END,
       NULL,
       d.day + time '18:00', %(user)s, d.day + time '18:00', %(user)s,
       k.kind % 50 = 3, CASE WHEN k.kind % 50 = 3 THEN 2 ELSE 1 END
FROM setup.fleet_vehicles AS f
CROSS JOIN LATERAL generate_series(f.joined_on, least(f.left_on - 1, %(today)s::date), interval '1 day') AS g(at)
CROSS JOIN LATERAL (SELECT g.at::date AS day) AS d
CROSS JOIN LATERAL (SELECT abs(hashtext(f.id::text || d.day::text)) % 100 AS kind) AS k
WHERE f.organization_id = %(org)s AND f.registration LIKE '%X'
  AND k.kind NOT BETWEEN 90 AND 92
  AND NOT (d.day = %(today)s::date AND abs(hashtext(f.registration)) % 10 < 3)
  AND NOT EXISTS (
    SELECT 1 FROM setup.vehicle_away_periods AS a
    WHERE a.organization_id = f.organization_id AND a.vehicle_id = f.id
      AND d.day >= a.left_on AND d.day < a.returned_on);
```

## Conditions

- Business date 2026-10-09 (a Friday); the week runs 2026-10-05 to 2026-10-11.
- The caller is an Owner with an all-companies scope and the `dash.capture` override, so every
  card is computed.
- PostgreSQL 16.15 on Windows 10, local: `shared_buffers` 128 MB, `work_mem` 4 MB, `jit` on;
  a 4-core laptop with 7.4 GB.
- The timings, burst figures and plans below were taken on a quiet machine (12% CPU, no other
  test run). The before and after table that follows was taken while two other sessions' test
  suites held the machine at 100% CPU: a plain `jsonb_build_object` over 3,500 rows took 117
  ms then, three to four times its quiet cost. Compare figures within one table.

## What the first measurement found, and the changes

First run, same seed, both columns at 100% CPU. The legacy week did not finish within the 5 s
`statement_timeout` of `xcode_app`. The last column is the same code on a quiet machine.

| Call | Before (ms) | After (ms) | After, quiet (ms) |
|---|---:|---:|---:|
| week, legacy form (first 500) | 4,854, then > 5,000 (timeout) | 732 | 233 |
| week, page 3 of 100 | 2,224 | 353 | 120 |
| week, one company | 1,051 | 98 | 44 |
| week, one vehicle a year back | 718 | 31 | 17 |
| dashboard, today | 880 | 33 | 25 |
| dashboard, week | 808 | 89 | 28 |
| dashboard, month | 832 | 90 | 41 |
| dashboard, month, one company | 804 | 22 | 12 |

1. `revenue.vehicle_days` joined `revenue.records` with no date bound. A SQL function with
   `SET search_path` is never inlined, so its body is planned without its arguments: the
   planner assumed 1,000 days per vehicle and hashed the organization's whole history (190,000
   rows) even for one vehicle's week. The records are now read for the period only, through
   `uq_records_vehicle_day` or `ix_records_business_date`.
2. `api.revenue_week_get` built each row's cells with a lateral subquery over the materialised
   grid, which rescanned every grid day for every row: 500 rows times 3,500 days. The page's
   days are now grouped once and hash-joined.
3. `revenue.earliest_missing` read each vehicle's whole history with a window function.
   - An open join date now answers at once.
   - Otherwise the vehicle's records are walked in date order, as an index-only scan, and the
     walk stops at the first open day: about 33 rows a vehicle here, instead of 380.
   - Time away is gathered once per vehicle into a multirange, instead of a scan per
     candidate day.
   - Cost over 500 vehicles: 834 ms before, 96 ms after.
4. `revenue.vehicle_week` was a SQL function called once per row. Each call started a new
   executor and planned the SQL helpers it calls (`round_half_even` and `percent`) again.
   - `vehicle_week` is now `plpgsql`, whose expressions keep their plans across calls: 1,877
     ms before, 693 ms after, for 500 rows.
   - `revenue.round_half_even` was a SQL function with `FROM`, so never inlined; it is now
     `plpgsql`: 171 ms before, 32 ms after, for 3,500 calls.
   - Every helper keeps `SET search_path = pg_catalog, pg_temp`.

No query runs per row inside a loop: `vehicle_week` loops over seven cells in memory. Every
read stays one routine call, budget 2 per request (`tests/api/test_revenue.py`).

## What remains

- **Week grid.** Its cost is the cells it builds. A page of 100 is 700 cells, and the legacy
  form (500 rows, 3,500 cells) is several times slower. That legacy form is what phones ask
  for, and it is also the web's first call: the web asks for pages of 100 only when the answer
  says `truncated` (`tests/api/test_revenue.py`, the web sequence).
  - `earliest_missing` and `first_gap` run over the whole filtered grid (490 vehicles here),
    whatever the page.
  - Worst case: a fleet whose history has no gap, where each vehicle's walk reads all its
    records. Over this seed that is 190,000 index entries, about 160 ms at full load,
    measured as a plain per-vehicle count.
  - A per-vehicle "complete through" summary maintained by capture would remove that cost. It
    is not built: it is a schema change, and the walk already stops early on any history
    with a gap.
- **Dashboard.** On the quiet machine the month card is 41 ms median and 63 ms at worst; the
  other periods are lower. That is under the 50 ms of `docs/05-routines.md` section 7, except
  the occasional slow run, and 90 ms at full load. Per that section, the operability prompt
  decides whether `revenue.dashboard_cache` is needed after measuring on the host.
- **Capture.** About 8 ms once warm. Every capture writes the organization row in
  `tenancy.record_change`, so one organization's captures queue on that row for the rest of
  their transaction (open question 32). 145 captures of the business date, each for a
  different vehicle:

  | Run | Captures a second | Median (ms) | p95 (ms) | Max (ms) |
  |---|---:|---:|---:|---:|
  | serial, quiet | 109.1 | 7.7 | 13.0 | 82 |
  | 8 concurrent connections, quiet | 155.7 | 12.2 | 48.9 | 530 |
  | serial, full load | 47.5 | 12.7 | 17.7 | 708 |
  | 8 concurrent connections, full load | 45.0 | 13.3 | 96.6 | 1,801 |

  Concurrency only overlaps the work before the organization row; at full load it adds
  nothing. A burst of 500 phones replaying at once clears in about three seconds on a quiet
  machine and eleven at full load. Inside the database a capture waits only for the captures
  holding the pool's other connections (`XCODE_DATABASE_POOL_MAX`, 10 by default, times about 13 ms), far from
  `statement_timeout`; the rest of the burst waits for a pool connection. The lock is held
  only for the rest of the capture's transaction.

## Timings

Milliseconds measured in Python around the routine call as `xcode_app`, without `auto_explain`; median and maximum of runs 3 to 7 of seven, and the first run. Captures run once each.

| Call | Median | Max | First |
|---|---:|---:|---:|
| week, legacy form (first 500) | 232.5 | 239.3 | 231.6 |
| week, page 3 of 100 | 119.8 | 121.4 | 103.7 |
| week, one company | 43.6 | 69.0 | 36.1 |
| week, one vehicle a year back | 16.9 | 30.0 | 32.1 |
| dashboard, today | 25.1 | 32.1 | 18.0 |
| dashboard, week | 27.9 | 31.8 | 39.5 |
| dashboard, month | 40.6 | 63.0 | 50.7 |
| dashboard, month, one company | 11.9 | 13.2 | 12.0 |
| capture, new record #1 | 26.0 |  |  |
| capture, new record #2 | 7.8 |  |  |
| capture, new record #3 | 9.6 |  |  |
| capture, identical replay | 8.1 |  |  |

Rows seeded: `setup.fleet_vehicles` 1002, `setup.vehicle_targets` 1307, `setup.vehicle_away_periods` 111, `revenue.records` 381659.
The legacy grid answered 490 of 490 vehicles (`truncated` false), `percent` 85, `first_gap` 2025-09-01.

## Plans

`EXPLAIN (ANALYZE, BUFFERS)` of the statements inside each routine, captured with `auto_explain` (`log_analyze`, `log_buffers`, `log_nested_statements`); per-node timing inflates the durations of statements with many small nodes. For each call: the routine statement's duration, then the plans of its four heaviest nested statements (a SQL function's body appears with its own text). Vehicle id arrays are elided.

### week, legacy form (first 500)

Routine statement: 460.2 ms; 526 nested statements logged.

357.4 ms: `WITH days AS MATERIALIZED ( SELECT d AS fact, d.vehicle_id, d.day, d.active, d.target, d.counted, d.record_id, d.amount FROM revenue.vehicle_days(v_gr ...`

```text
Subquery Scan on t  (cost=459.39..460.15 rows=1 width=32) (actual time=356.649..356.667 rows=1 loops=1)
  Buffers: shared hit=7066
  CTE days
    ->  Function Scan on vehicle_days d_1  (cost=0.25..10.25 rows=1000 width=228) (actual time=50.852..52.059 rows=3430 loops=1)
          Buffers: shared hit=3476
  CTE missing
    ->  Function Scan on earliest_missing m  (cost=0.25..10.25 rows=1000 width=20) (actual time=38.642..38.690 rows=490 loops=1)
          Buffers: shared hit=3250
  InitPlan 3 (returns $2)
    ->  Aggregate  (cost=228.14..228.15 rows=1 width=32) (actual time=280.915..280.924 rows=1 loops=1)
          Buffers: shared hit=3590
          ->  Sort  (cost=164.43..165.05 rows=245 width=104) (actual time=44.256..44.497 rows=490 loops=1)
                Sort Key: s.ord
                Sort Method: quicksort  Memory: 370kB
                Buffers: shared hit=3268
                ->  Result  (cost=123.51..154.71 rows=245 width=104) (actual time=43.156..43.758 rows=490 loops=1)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                      Buffers: shared hit=3265
                      ->  Hash Right Join  (cost=123.51..154.71 rows=245 width=104) (actual time=43.148..43.670 rows=490 loops=1)
                            Hash Cond: (m_1.vehicle_id = s.id)
                            Buffers: shared hit=3265
                            ->  CTE Scan on missing m_1  (cost=0.00..20.00 rows=1000 width=20) (actual time=38.645..38.836 rows=490 loops=1)
                                  Buffers: shared hit=3250
                            ->  Hash  (cost=122.89..122.89 rows=49 width=116) (actual time=4.489..4.495 rows=490 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 365kB
                                  Buffers: shared hit=15
                                  ->  Hash Join  (cost=115.51..122.89 rows=49 width=116) (actual time=3.532..3.938 rows=490 loops=1)
                                        Hash Cond: (f.company_id = c.id)
                                        Buffers: shared hit=15
                                        ->  Hash Join  (cost=114.12..121.35 rows=49 width=121) (actual time=3.501..3.752 rows=490 loops=1)
                                              Hash Cond: (s.id = f.id)
                                              Buffers: shared hit=14
                                              ->  Function Scan on unnest s  (cost=0.00..4.90 rows=490 width=24) (actual time=0.049..0.093 rows=490 loops=1)
                                              ->  Hash  (cost=112.87..112.87 rows=100 width=113) (actual time=3.444..3.448 rows=490 loops=1)
                                                    Buckets: 1024  Batches: 1  Memory Usage: 358kB
                                                    Buffers: shared hit=14
                                                    ->  Hash Join  (cost=85.03..112.87 rows=100 width=113) (actual time=2.846..3.112 rows=490 loops=1)
                                                          Hash Cond: (f.id = w.vehicle_id)
                                                          Buffers: shared hit=14
                                                          ->  Seq Scan on fleet_vehicles f  (cost=0.00..26.52 rows=500 width=65) (actual time=0.009..0.135 rows=500 loops=1)
                                                                Filter: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                                                                Rows Removed by Filter: 502
                                                                Buffers: shared hit=14
                                                          ->  Hash  (cost=82.53..82.53 rows=200 width=48) (actual time=2.830..2.832 rows=490 loops=1)
                                                                Buckets: 1024  Batches: 1  Memory Usage: 327kB
                                                                ->  Subquery Scan on w  (cost=71.18..82.53 rows=200 width=48) (actual time=1.591..2.558 rows=490 loops=1)
                                                                      ->  GroupAggregate  (cost=71.18..80.53 rows=200 width=48) (actual time=1.590..2.508 rows=490 loops=1)
                                                                            Group Key: d_2.vehicle_id
                                                                            ->  Sort  (cost=71.18..73.46 rows=914 width=52) (actual time=1.583..1.713 rows=3430 loops=1)
                                                                                  Sort Key: d_2.vehicle_id, d_2.day
                                                                                  Sort Method: quicksort  Memory: 532kB
                                                                                  ->  CTE Scan on days d_2  (cost=1.23..26.23 rows=914 width=52) (actual time=0.029..0.673 rows=3430 loops=1)
                                                                                        Filter: (vehicle_id = ANY ('{...}'::uuid[]))
                                        ->  Hash  (cost=1.26..1.26 rows=10 width=43) (actual time=0.026..0.026 rows=10 loops=1)
                                              Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                              Buffers: shared hit=1
                                              ->  Seq Scan on psv_companies c  (cost=0.00..1.26 rows=10 width=43) (actual time=0.020..0.023 rows=10 loops=1)
                                                    Filter: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                                                    Rows Removed by Filter: 11
                                                    Buffers: shared hit=1
  InitPlan 4 (returns $3)
    ->  Aggregate  (cost=29.72..29.73 rows=1 width=32) (actual time=5.089..5.092 rows=1 loops=1)
          ->  Sort  (cost=26.15..26.17 rows=7 width=68) (actual time=4.883..4.887 rows=7 loops=1)
                Sort Key: dt.day
                Sort Method: quicksort  Memory: 25kB
                ->  Subquery Scan on dt  (cost=25.86..26.05 rows=7 width=68) (actual time=4.864..4.872 rows=7 loops=1)
                      ->  HashAggregate  (cost=25.86..25.98 rows=7 width=72) (actual time=4.862..4.869 rows=7 loops=1)
                            Group Key: n.offset_days
                            Batches: 1  Memory Usage: 24kB
                            ->  Hash Right Join  (cost=0.16..25.51 rows=35 width=74) (actual time=0.022..2.793 rows=3430 loops=1)
                                  Hash Cond: (d_3.day = ('2026-10-05'::date + n.offset_days))
                                  ->  CTE Scan on days d_3  (cost=0.00..20.00 rows=1000 width=70) (actual time=0.001..0.676 rows=3430 loops=1)
                                  ->  Hash  (cost=0.07..0.07 rows=7 width=4) (actual time=0.012..0.012 rows=7 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                        ->  Function Scan on generate_series n  (cost=0.00..0.07 rows=7 width=4) (actual time=0.007..0.007 rows=7 loops=1)
  InitPlan 5 (returns $4)
    ->  Subquery Scan on g  (cost=155.99..156.00 rows=1 width=32) (actual time=2.373..2.378 rows=1 loops=1)
          ->  Limit  (cost=155.99..155.99 rows=1 width=28) (actual time=2.360..2.363 rows=1 loops=1)
                ->  Sort  (cost=155.99..162.08 rows=2438 width=28) (actual time=2.358..2.361 rows=1 loops=1)
                      Sort Key: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END)), g_1.ord
                      Sort Method: top-N heapsort  Memory: 25kB
                      ->  Hash Right Join  (cost=35.55..143.80 rows=2438 width=28) (actual time=1.925..2.252 rows=490 loops=1)
                            Hash Cond: (m_2.vehicle_id = g_1.id)
                            Filter: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END) IS NOT NULL)
                            ->  CTE Scan on missing m_2  (cost=0.00..20.00 rows=1000 width=20) (actual time=0.001..0.065 rows=490 loops=1)
                            ->  Hash  (cost=29.42..29.42 rows=490 width=41) (actual time=1.909..1.910 rows=490 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 41kB
                                  ->  Hash Left Join  (cost=22.57..29.42 rows=490 width=41) (actual time=1.408..1.708 rows=490 loops=1)
                                        Hash Cond: (g_1.id = t_1.vehicle_id)
                                        ->  Function Scan on unnest g_1  (cost=0.00..4.90 rows=490 width=24) (actual time=0.063..0.126 rows=490 loops=1)
                                        ->  Hash  (cost=22.50..22.50 rows=5 width=33) (actual time=1.332..1.333 rows=490 loops=1)
                                              Buckets: 1024  Batches: 1  Memory Usage: 37kB
                                              ->  CTE Scan on days t_1  (cost=0.00..22.50 rows=5 width=33) (actual time=0.029..1.071 rows=490 loops=1)
                                                    Filter: (day = '2026-10-09'::date)
                                                    Rows Removed by Filter: 2940
  ->  Aggregate  (cost=25.00..25.02 rows=1 width=64) (actual time=54.160..54.161 rows=1 loops=1)
        Buffers: shared hit=3476
        ->  CTE Scan on days d  (cost=0.00..20.00 rows=1000 width=65) (actual time=50.854..53.511 rows=3430 loops=1)
              Buffers: shared hit=3476
```

36.0 ms: `SELECT tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view')`

```text
Result  (cost=0.00..0.26 rows=1 width=4) (actual time=36.046..36.046 rows=1 loops=1)
  Buffers: shared hit=975
```

35.2 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=19.945..33.025 rows=3430 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 1043
  Buffers: shared hit=2997
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=18.666..23.508 rows=3430 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 371
        Buffers: shared hit=2005
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=18.192..21.657 rows=3430 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=2003
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=6.090..6.650 rows=3430 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 284kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.068..2.609 rows=3430 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.005..0.008 rows=7 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.009..0.188 rows=490 loops=7)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.044..0.947 rows=490 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 10
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.032..0.032 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=12.096..12.275 rows=2234 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 289kB
                    Buffers: shared hit=1995
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.326..10.693 rows=2234 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 8555
                          Buffers: shared hit=1995
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.277..7.670 rows=2234 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=1994
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.000 rows=4 loops=2234)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.038..0.040 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.471..0.498 rows=367 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.041..0.444 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=1.275..3.455 rows=4467 loops=1)
        Buffers: shared hit=992
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=1.271..2.875 rows=639 loops=1)
              Buffers: shared hit=992
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=1.257..1.790 rows=639 loops=1)
                    Buffers: shared hit=992
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=1.256..1.638 rows=639 loops=1)
                          Buffers: shared hit=992
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=1.256..1.397 rows=639 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 59kB
                                Buffers: shared hit=992
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=0.886..1.046 rows=639 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=989
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=0.872..0.872 rows=639 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=980
```

34.1 ms: `WITH vehicles AS ( SELECT f.organization_id, f.id, f.joined_on, CASE WHEN f.left_on < p_today THEN f.left_on ELSE p_today END AS end_on FROM setup.fle ...`

```text
Nested Loop Left Join  (cost=13.85..213.98 rows=5 width=20) (actual time=0.902..33.948 rows=490 loops=1)
  Join Filter: (w.vehicle_id = f.id)
  Rows Removed by Join Filter: 24539
  Buffers: shared hit=3159
  ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=40) (actual time=0.037..1.082 rows=490 loops=1)
        Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
        Filter: (id = ANY ($1))
        Rows Removed by Filter: 10
        Heap Blocks: exact=7
        Buffers: shared hit=8
        ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.028..0.029 rows=500 loops=1)
              Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
              Buffers: shared hit=1
  ->  Materialize  (cost=5.93..6.08 rows=5 width=80) (actual time=0.001..0.003 rows=50 loops=490)
        Buffers: shared hit=2
        ->  Subquery Scan on w  (cost=5.93..6.06 rows=5 width=80) (actual time=0.584..0.604 rows=53 loops=1)
              Buffers: shared hit=2
              ->  HashAggregate  (cost=5.93..6.01 rows=5 width=80) (actual time=0.584..0.600 rows=53 loops=1)
                    Group Key: a.vehicle_id
                    Batches: 1  Memory Usage: 48kB
                    Buffers: shared hit=2
                    ->  Seq Scan on vehicle_away_periods a  (cost=0.00..5.88 rows=5 width=24) (actual time=0.013..0.447 rows=53 loops=1)
                          Filter: ((vehicle_id = ANY ($1)) AND (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid))
                          Rows Removed by Filter: 58
                          Buffers: shared hit=2
  SubPlan 1
    ->  Result  (cost=0.42..8.44 rows=1 width=0) (actual time=0.009..0.009 rows=1 loops=490)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
          Buffers: shared hit=1471
          ->  Index Only Scan using uq_records_vehicle_day on records r  (cost=0.42..8.44 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=490)
                Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = f.joined_on))
                Heap Fetches: 0
                Buffers: shared hit=1471
  SubPlan 2
    ->  Limit  (cost=0.42..8.49 rows=1 width=8) (actual time=0.044..0.044 rows=1 loops=476)
          Buffers: shared hit=1521
          ->  Subquery Scan on g  (cost=0.42..8.49 rows=1 width=8) (actual time=0.044..0.044 rows=1 loops=476)
                Filter: ((g.following IS DISTINCT FROM g.next_day) AND (NOT COALESCE((w.spans @> g.next_day), false)) AND (g.next_day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                Rows Removed by Filter: 31
                Buffers: shared hit=1521
                ->  WindowAgg  (cost=0.42..8.47 rows=1 width=12) (actual time=0.015..0.040 rows=32 loops=476)
                      Buffers: shared hit=1521
                      ->  Result  (cost=0.42..8.45 rows=1 width=4) (actual time=0.013..0.022 rows=33 loops=476)
                            One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                            Buffers: shared hit=1521
                            ->  Index Only Scan using uq_records_vehicle_day on records r_1  (cost=0.42..8.45 rows=1 width=4) (actual time=0.009..0.015 rows=33 loops=476)
                                  Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date >= f.joined_on) AND (business_date < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                                  Heap Fetches: 0
                                  Buffers: shared hit=1521
  SubPlan 3
    ->  Aggregate  (cost=16.67..16.68 rows=1 width=4) (actual time=0.003..0.003 rows=1 loops=476)
          Buffers: shared hit=157
          ->  Nested Loop Anti Join  (cost=0.42..16.67 rows=1 width=4) (actual time=0.003..0.003 rows=0 loops=476)
                Buffers: shared hit=157
                ->  Function Scan on unnest x  (cost=0.00..0.20 rows=1 width=4) (actual time=0.001..0.001 rows=0 loops=476)
                      Filter: ((day > f.joined_on) AND (day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END) AND (NOT (w.spans @> day)))
                ->  Result  (cost=0.42..8.44 rows=1 width=4) (actual time=0.012..0.013 rows=1 loops=52)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                      Buffers: shared hit=157
                      ->  Index Only Scan using uq_records_vehicle_day on records r_2  (cost=0.42..8.44 rows=1 width=4) (actual time=0.008..0.008 rows=1 loops=52)
                            Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = x.day))
                            Heap Fetches: 0
                            Buffers: shared hit=157
```

### week, page 3 of 100

Routine statement: 190.0 ms; 137 nested statements logged.

143.9 ms: `WITH days AS MATERIALIZED ( SELECT d AS fact, d.vehicle_id, d.day, d.active, d.target, d.counted, d.record_id, d.amount FROM revenue.vehicle_days(v_gr ...`

```text
Subquery Scan on t  (cost=359.76..360.52 rows=1 width=32) (actual time=143.901..143.917 rows=1 loops=1)
  Buffers: shared hit=6173
  CTE days
    ->  Function Scan on vehicle_days d_1  (cost=0.25..10.25 rows=1000 width=228) (actual time=42.173..45.817 rows=3430 loops=1)
          Buffers: shared hit=2999
  CTE missing
    ->  Function Scan on earliest_missing m  (cost=0.25..10.25 rows=1000 width=20) (actual time=38.223..38.247 rows=490 loops=1)
          Buffers: shared hit=3159
  InitPlan 3 (returns $2)
    ->  Aggregate  (cost=128.50..128.51 rows=1 width=32) (actual time=84.445..84.452 rows=1 loops=1)
          Buffers: shared hit=3174
          ->  Sort  (cost=116.02..116.14 rows=48 width=104) (actual time=41.691..41.754 rows=100 loops=1)
                Sort Key: s.ord
                Sort Method: quicksort  Memory: 95kB
                Buffers: shared hit=3174
                ->  Result  (cost=90.28..114.68 rows=48 width=104) (actual time=41.376..41.608 rows=100 loops=1)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                      Buffers: shared hit=3174
                      ->  Hash Join  (cost=90.28..114.68 rows=48 width=104) (actual time=41.356..41.577 rows=100 loops=1)
                            Hash Cond: (f.company_id = c.id)
                            Buffers: shared hit=3174
                            ->  Hash Right Join  (cost=88.88..113.13 rows=48 width=109) (actual time=41.255..41.452 rows=100 loops=1)
                                  Hash Cond: (m_1.vehicle_id = s.id)
                                  Buffers: shared hit=3173
                                  ->  CTE Scan on missing m_1  (cost=0.00..20.00 rows=1000 width=20) (actual time=38.227..38.342 rows=490 loops=1)
                                        Buffers: shared hit=3159
                                  ->  Hash  (cost=88.76..88.76 rows=10 width=121) (actual time=3.011..3.015 rows=100 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 81kB
                                        Buffers: shared hit=14
                                        ->  Hash Join  (cost=60.46..88.76 rows=10 width=121) (actual time=2.338..2.830 rows=100 loops=1)
                                              Hash Cond: (f.id = s.id)
                                              Buffers: shared hit=14
                                              ->  Hash Join  (cost=58.20..86.04 rows=97 width=113) (actual time=2.247..2.661 rows=100 loops=1)
                                                    Hash Cond: (f.id = w.vehicle_id)
                                                    Buffers: shared hit=14
                                                    ->  Seq Scan on fleet_vehicles f  (cost=0.00..26.52 rows=500 width=65) (actual time=0.022..0.285 rows=500 loops=1)
                                                          Filter: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                                                          Rows Removed by Filter: 502
                                                          Buffers: shared hit=14
                                                    ->  Hash  (cost=55.78..55.78 rows=194 width=48) (actual time=2.193..2.194 rows=100 loops=1)
                                                          Buckets: 1024  Batches: 1  Memory Usage: 74kB
                                                          ->  Subquery Scan on w  (cost=47.66..55.78 rows=194 width=48) (actual time=1.592..2.061 rows=100 loops=1)
                                                                ->  GroupAggregate  (cost=47.66..53.84 rows=194 width=48) (actual time=1.590..2.037 rows=100 loops=1)
                                                                      Group Key: d_2.vehicle_id
                                                                      ->  Sort  (cost=47.66..48.91 rows=500 width=52) (actual time=1.564..1.616 rows=700 loops=1)
                                                                            Sort Key: d_2.vehicle_id, d_2.day
                                                                            Sort Method: quicksort  Memory: 114kB
                                                                            ->  CTE Scan on days d_2  (cost=0.25..25.25 rows=500 width=52) (actual time=0.012..1.201 rows=700 loops=1)
                                                                                  Filter: (vehicle_id = ANY ('{...}'::uuid[]))
                                                                                  Rows Removed by Filter: 2730
                                              ->  Hash  (cost=1.00..1.00 rows=100 width=24) (actual time=0.079..0.080 rows=100 loops=1)
                                                    Buckets: 1024  Batches: 1  Memory Usage: 14kB
                                                    ->  Function Scan on unnest s  (cost=0.00..1.00 rows=100 width=24) (actual time=0.031..0.046 rows=100 loops=1)
                            ->  Hash  (cost=1.26..1.26 rows=10 width=43) (actual time=0.085..0.086 rows=10 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                  Buffers: shared hit=1
                                  ->  Seq Scan on psv_companies c  (cost=0.00..1.26 rows=10 width=43) (actual time=0.059..0.065 rows=10 loops=1)
                                        Filter: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                                        Rows Removed by Filter: 11
                                        Buffers: shared hit=1
  InitPlan 4 (returns $3)
    ->  Aggregate  (cost=29.72..29.73 rows=1 width=32) (actual time=4.199..4.201 rows=1 loops=1)
          ->  Sort  (cost=26.15..26.17 rows=7 width=68) (actual time=3.995..3.999 rows=7 loops=1)
                Sort Key: dt.day
                Sort Method: quicksort  Memory: 25kB
                ->  Subquery Scan on dt  (cost=25.86..26.05 rows=7 width=68) (actual time=3.960..3.969 rows=7 loops=1)
                      ->  HashAggregate  (cost=25.86..25.98 rows=7 width=72) (actual time=3.959..3.966 rows=7 loops=1)
                            Group Key: n.offset_days
                            Batches: 1  Memory Usage: 24kB
                            ->  Hash Right Join  (cost=0.16..25.51 rows=35 width=74) (actual time=0.032..2.332 rows=3430 loops=1)
                                  Hash Cond: (d_3.day = ('2026-10-05'::date + n.offset_days))
                                  ->  CTE Scan on days d_3  (cost=0.00..20.00 rows=1000 width=70) (actual time=0.001..0.609 rows=3430 loops=1)
                                  ->  Hash  (cost=0.07..0.07 rows=7 width=4) (actual time=0.022..0.023 rows=7 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                        ->  Function Scan on generate_series n  (cost=0.00..0.07 rows=7 width=4) (actual time=0.012..0.013 rows=7 loops=1)
  InitPlan 5 (returns $4)
    ->  Subquery Scan on g  (cost=155.99..156.00 rows=1 width=32) (actual time=1.900..1.904 rows=1 loops=1)
          ->  Limit  (cost=155.99..155.99 rows=1 width=28) (actual time=1.884..1.888 rows=1 loops=1)
                ->  Sort  (cost=155.99..162.08 rows=2438 width=28) (actual time=1.883..1.885 rows=1 loops=1)
                      Sort Key: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END)), g_1.ord
                      Sort Method: top-N heapsort  Memory: 25kB
                      ->  Hash Right Join  (cost=35.55..143.80 rows=2438 width=28) (actual time=1.438..1.784 rows=490 loops=1)
                            Hash Cond: (m_2.vehicle_id = g_1.id)
                            Filter: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END) IS NOT NULL)
                            ->  CTE Scan on missing m_2  (cost=0.00..20.00 rows=1000 width=20) (actual time=0.001..0.053 rows=490 loops=1)
                            ->  Hash  (cost=29.42..29.42 rows=490 width=41) (actual time=1.428..1.429 rows=490 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 41kB
                                  ->  Hash Left Join  (cost=22.57..29.42 rows=490 width=41) (actual time=0.992..1.266 rows=490 loops=1)
                                        Hash Cond: (g_1.id = t_1.vehicle_id)
                                        ->  Function Scan on unnest g_1  (cost=0.00..4.90 rows=490 width=24) (actual time=0.091..0.142 rows=490 loops=1)
                                        ->  Hash  (cost=22.50..22.50 rows=5 width=33) (actual time=0.887..0.887 rows=490 loops=1)
                                              Buckets: 1024  Batches: 1  Memory Usage: 37kB
                                              ->  CTE Scan on days t_1  (cost=0.00..22.50 rows=5 width=33) (actual time=0.003..0.713 rows=490 loops=1)
                                                    Filter: (day = '2026-10-09'::date)
                                                    Rows Removed by Filter: 2940
  ->  Aggregate  (cost=25.00..25.02 rows=1 width=64) (actual time=50.229..50.229 rows=1 loops=1)
        Buffers: shared hit=2999
        ->  CTE Scan on days d  (cost=0.00..20.00 rows=1000 width=65) (actual time=42.181..48.806 rows=3430 loops=1)
              Buffers: shared hit=2999
```

35.8 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=19.333..33.449 rows=3430 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 1043
  Buffers: shared hit=2991
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=18.000..23.477 rows=3430 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 371
        Buffers: shared hit=2002
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=17.441..21.561 rows=3430 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=2000
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=9.372..10.073 rows=3430 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 284kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.124..4.927 rows=3430 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.018..0.024 rows=7 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.015..0.454 rows=490 loops=7)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.095..2.386 rows=490 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 10
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.074..0.075 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=8.062..8.298 rows=2234 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 289kB
                    Buffers: shared hit=1992
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.238..6.536 rows=2234 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 8555
                          Buffers: shared hit=1992
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.202..3.269 rows=2234 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=1991
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.000 rows=4 loops=2234)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.021..0.021 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.557..0.588 rows=367 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.038..0.524 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=1.328..4.195 rows=4467 loops=1)
        Buffers: shared hit=989
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=1.322..3.573 rows=639 loops=1)
              Buffers: shared hit=989
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=1.310..1.991 rows=639 loops=1)
                    Buffers: shared hit=989
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=1.309..1.797 rows=639 loops=1)
                          Buffers: shared hit=989
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=1.308..1.490 rows=639 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 59kB
                                Buffers: shared hit=989
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=0.976..1.100 rows=639 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=989
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=0.968..0.968 rows=639 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=980
```

34.0 ms: `WITH vehicles AS ( SELECT f.organization_id, f.id, f.joined_on, CASE WHEN f.left_on < p_today THEN f.left_on ELSE p_today END AS end_on FROM setup.fle ...`

```text
Nested Loop Left Join  (cost=13.85..213.98 rows=5 width=20) (actual time=1.058..33.737 rows=490 loops=1)
  Join Filter: (w.vehicle_id = f.id)
  Rows Removed by Join Filter: 24539
  Buffers: shared hit=3159
  ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=40) (actual time=0.096..1.267 rows=490 loops=1)
        Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
        Filter: (id = ANY ($1))
        Rows Removed by Filter: 10
        Heap Blocks: exact=7
        Buffers: shared hit=8
        ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.075..0.076 rows=500 loops=1)
              Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
              Buffers: shared hit=1
  ->  Materialize  (cost=5.93..6.08 rows=5 width=80) (actual time=0.002..0.004 rows=50 loops=490)
        Buffers: shared hit=2
        ->  Subquery Scan on w  (cost=5.93..6.06 rows=5 width=80) (actual time=0.808..0.845 rows=53 loops=1)
              Buffers: shared hit=2
              ->  HashAggregate  (cost=5.93..6.01 rows=5 width=80) (actual time=0.807..0.837 rows=53 loops=1)
                    Group Key: a.vehicle_id
                    Batches: 1  Memory Usage: 48kB
                    Buffers: shared hit=2
                    ->  Seq Scan on vehicle_away_periods a  (cost=0.00..5.88 rows=5 width=24) (actual time=0.026..0.708 rows=53 loops=1)
                          Filter: ((vehicle_id = ANY ($1)) AND (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid))
                          Rows Removed by Filter: 58
                          Buffers: shared hit=2
  SubPlan 1
    ->  Result  (cost=0.42..8.44 rows=1 width=0) (actual time=0.010..0.010 rows=1 loops=490)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
          Buffers: shared hit=1471
          ->  Index Only Scan using uq_records_vehicle_day on records r  (cost=0.42..8.44 rows=1 width=0) (actual time=0.005..0.005 rows=1 loops=490)
                Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = f.joined_on))
                Heap Fetches: 0
                Buffers: shared hit=1471
  SubPlan 2
    ->  Limit  (cost=0.42..8.49 rows=1 width=8) (actual time=0.041..0.041 rows=1 loops=476)
          Buffers: shared hit=1521
          ->  Subquery Scan on g  (cost=0.42..8.49 rows=1 width=8) (actual time=0.041..0.041 rows=1 loops=476)
                Filter: ((g.following IS DISTINCT FROM g.next_day) AND (NOT COALESCE((w.spans @> g.next_day), false)) AND (g.next_day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                Rows Removed by Filter: 31
                Buffers: shared hit=1521
                ->  WindowAgg  (cost=0.42..8.47 rows=1 width=12) (actual time=0.015..0.037 rows=32 loops=476)
                      Buffers: shared hit=1521
                      ->  Result  (cost=0.42..8.45 rows=1 width=4) (actual time=0.013..0.021 rows=33 loops=476)
                            One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                            Buffers: shared hit=1521
                            ->  Index Only Scan using uq_records_vehicle_day on records r_1  (cost=0.42..8.45 rows=1 width=4) (actual time=0.008..0.014 rows=33 loops=476)
                                  Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date >= f.joined_on) AND (business_date < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                                  Heap Fetches: 0
                                  Buffers: shared hit=1521
  SubPlan 3
    ->  Aggregate  (cost=16.67..16.68 rows=1 width=4) (actual time=0.004..0.004 rows=1 loops=476)
          Buffers: shared hit=157
          ->  Nested Loop Anti Join  (cost=0.42..16.67 rows=1 width=4) (actual time=0.003..0.003 rows=0 loops=476)
                Buffers: shared hit=157
                ->  Function Scan on unnest x  (cost=0.00..0.20 rows=1 width=4) (actual time=0.001..0.001 rows=0 loops=476)
                      Filter: ((day > f.joined_on) AND (day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END) AND (NOT (w.spans @> day)))
                ->  Result  (cost=0.42..8.44 rows=1 width=4) (actual time=0.010..0.010 rows=1 loops=52)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                      Buffers: shared hit=157
                      ->  Index Only Scan using uq_records_vehicle_day on records r_2  (cost=0.42..8.44 rows=1 width=4) (actual time=0.005..0.005 rows=1 loops=52)
                            Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = x.day))
                            Heap Fetches: 0
                            Buffers: shared hit=157
```

9.3 ms: `SELECT tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view')`

```text
Result  (cost=0.00..0.26 rows=1 width=4) (actual time=9.327..9.328 rows=1 loops=1)
  Buffers: shared hit=10
```

### week, one company

Routine statement: 96.3 ms; 87 nested statements logged.

65.8 ms: `WITH days AS MATERIALIZED ( SELECT d AS fact, d.vehicle_id, d.day, d.active, d.target, d.counted, d.record_id, d.amount FROM revenue.vehicle_days(v_gr ...`

```text
Subquery Scan on t  (cost=228.04..228.81 rows=1 width=32) (actual time=65.752..65.772 rows=1 loops=1)
  Buffers: shared hit=766
  CTE days
    ->  Function Scan on vehicle_days d_1  (cost=0.25..10.25 rows=1000 width=228) (actual time=8.962..9.214 rows=350 loops=1)
          Buffers: shared hit=333
  CTE missing
    ->  Function Scan on earliest_missing m  (cost=0.25..10.25 rows=1000 width=20) (actual time=8.042..8.078 rows=50 loops=1)
          Buffers: shared hit=319
  InitPlan 3 (returns $3)
    ->  Aggregate  (cost=101.40..101.41 rows=1 width=32) (actual time=52.522..52.531 rows=1 loops=1)
          Buffers: shared hit=433
          ->  Sort  (cost=96.46..96.50 rows=19 width=104) (actual time=9.416..11.240 rows=50 loops=1)
                Sort Key: s.ord
                Sort Method: quicksort  Memory: 60kB
                Buffers: shared hit=433
                ->  Result  (cost=72.10..96.05 rows=19 width=104) (actual time=9.225..9.362 rows=50 loops=1)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                      Buffers: shared hit=433
                      ->  Hash Right Join  (cost=72.10..96.05 rows=19 width=104) (actual time=9.217..9.339 rows=50 loops=1)
                            Hash Cond: (m_1.vehicle_id = s.id)
                            Buffers: shared hit=433
                            ->  CTE Scan on missing m_1  (cost=0.00..20.00 rows=1000 width=20) (actual time=8.046..8.101 rows=50 loops=1)
                                  Buffers: shared hit=319
                            ->  Hash  (cost=72.04..72.04 rows=4 width=116) (actual time=1.162..1.168 rows=50 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 45kB
                                  Buffers: shared hit=114
                                  ->  Nested Loop  (cost=65.58..72.04 rows=4 width=116) (actual time=0.732..1.128 rows=50 loops=1)
                                        Buffers: shared hit=114
                                        ->  Merge Join  (cost=65.44..71.31 rows=4 width=121) (actual time=0.707..0.977 rows=50 loops=1)
                                              Merge Cond: (f.id = d_2.vehicle_id)
                                              Buffers: shared hit=14
                                              ->  Sort  (cost=30.36..30.42 rows=25 width=89) (actual time=0.361..0.369 rows=50 loops=1)
                                                    Sort Key: s.id
                                                    Sort Method: quicksort  Memory: 30kB
                                                    Buffers: shared hit=14
                                                    ->  Hash Join  (cost=1.13..29.78 rows=25 width=89) (actual time=0.077..0.338 rows=50 loops=1)
                                                          Hash Cond: (f.id = s.id)
                                                          Buffers: shared hit=14
                                                          ->  Seq Scan on fleet_vehicles f  (cost=0.00..26.52 rows=500 width=65) (actual time=0.020..0.197 rows=500 loops=1)
                                                                Filter: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                                                                Rows Removed by Filter: 502
                                                                Buffers: shared hit=14
                                                          ->  Hash  (cost=0.50..0.50 rows=50 width=24) (actual time=0.049..0.051 rows=50 loops=1)
                                                                Buckets: 1024  Batches: 1  Memory Usage: 11kB
                                                                ->  Function Scan on unnest s  (cost=0.00..0.50 rows=50 width=24) (actual time=0.016..0.020 rows=50 loops=1)
                                              ->  GroupAggregate  (cost=35.08..38.87 rows=153 width=48) (actual time=0.329..0.545 rows=50 loops=1)
                                                    Group Key: d_2.vehicle_id
                                                    ->  Sort  (cost=35.08..35.71 rows=250 width=52) (actual time=0.319..0.340 rows=350 loops=1)
                                                          Sort Key: d_2.vehicle_id, d_2.day
                                                          Sort Method: quicksort  Memory: 69kB
                                                          ->  CTE Scan on days d_2  (cost=0.12..25.12 rows=250 width=52) (actual time=0.008..0.163 rows=350 loops=1)
                                                                Filter: (vehicle_id = ANY ('{...}'::uuid[]))
                                        ->  Index Scan using pk_psv_companies on psv_companies c  (cost=0.14..0.18 rows=1 width=43) (actual time=0.002..0.002 rows=1 loops=50)
                                              Index Cond: ((organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid) AND (id = f.company_id))
                                              Buffers: shared hit=100
  InitPlan 4 (returns $4)
    ->  Aggregate  (cost=29.72..29.73 rows=1 width=32) (actual time=0.927..0.930 rows=1 loops=1)
          ->  Sort  (cost=26.15..26.17 rows=7 width=68) (actual time=0.715..0.718 rows=7 loops=1)
                Sort Key: dt.day
                Sort Method: quicksort  Memory: 25kB
                ->  Subquery Scan on dt  (cost=25.86..26.05 rows=7 width=68) (actual time=0.693..0.706 rows=7 loops=1)
                      ->  HashAggregate  (cost=25.86..25.98 rows=7 width=72) (actual time=0.691..0.703 rows=7 loops=1)
                            Group Key: n.offset_days
                            Batches: 1  Memory Usage: 24kB
                            ->  Hash Right Join  (cost=0.16..25.51 rows=35 width=74) (actual time=0.036..0.411 rows=350 loops=1)
                                  Hash Cond: (d_3.day = ('2026-10-05'::date + n.offset_days))
                                  ->  CTE Scan on days d_3  (cost=0.00..20.00 rows=1000 width=70) (actual time=0.001..0.075 rows=350 loops=1)
                                  ->  Hash  (cost=0.07..0.07 rows=7 width=4) (actual time=0.023..0.024 rows=7 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                        ->  Function Scan on generate_series n  (cost=0.00..0.07 rows=7 width=4) (actual time=0.012..0.013 rows=7 loops=1)
  InitPlan 5 (returns $5)
    ->  Subquery Scan on g  (cost=51.38..51.40 rows=1 width=32) (actual time=0.352..0.356 rows=1 loops=1)
          ->  Limit  (cost=51.38..51.38 rows=1 width=28) (actual time=0.345..0.347 rows=1 loops=1)
                ->  Sort  (cost=51.38..52.01 rows=249 width=28) (actual time=0.343..0.346 rows=1 loops=1)
                      Sort Key: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END)), g_1.ord
                      Sort Method: top-N heapsort  Memory: 25kB
                      ->  Hash Right Join  (cost=23.89..50.14 rows=249 width=28) (actual time=0.262..0.318 rows=50 loops=1)
                            Hash Cond: (m_2.vehicle_id = g_1.id)
                            Filter: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END) IS NOT NULL)
                            ->  CTE Scan on missing m_2  (cost=0.00..20.00 rows=1000 width=20) (actual time=0.001..0.009 rows=50 loops=1)
                            ->  Hash  (cost=23.26..23.26 rows=50 width=41) (actual time=0.252..0.254 rows=50 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 12kB
                                  ->  Hash Left Join  (cost=22.57..23.26 rows=50 width=41) (actual time=0.183..0.223 rows=50 loops=1)
                                        Hash Cond: (g_1.id = t_1.vehicle_id)
                                        ->  Function Scan on unnest g_1  (cost=0.00..0.50 rows=50 width=24) (actual time=0.020..0.028 rows=50 loops=1)
                                        ->  Hash  (cost=22.50..22.50 rows=5 width=33) (actual time=0.158..0.159 rows=50 loops=1)
                                              Buckets: 1024  Batches: 1  Memory Usage: 11kB
                                              ->  CTE Scan on days t_1  (cost=0.00..22.50 rows=5 width=33) (actual time=0.004..0.132 rows=50 loops=1)
                                                    Filter: (day = '2026-10-09'::date)
                                                    Rows Removed by Filter: 300
  ->  Aggregate  (cost=25.00..25.02 rows=1 width=64) (actual time=9.649..9.650 rows=1 loops=1)
        Buffers: shared hit=333
        ->  CTE Scan on days d  (cost=0.00..20.00 rows=1000 width=65) (actual time=8.965..9.499 rows=350 loops=1)
              Buffers: shared hit=333
```

5.1 ms: `SELECT tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view')`

```text
Result  (cost=0.00..0.26 rows=1 width=4) (actual time=5.145..5.145 rows=1 loops=1)
  Buffers: shared hit=10
```

5.0 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=5.024..5.026 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.017..0.018 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.010..0.010 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

4.8 ms: `WITH vehicles AS ( SELECT f.organization_id, f.id, f.joined_on, CASE WHEN f.left_on < p_today THEN f.left_on ELSE p_today END AS end_on FROM setup.fle ...`

```text
Nested Loop Left Join  (cost=13.85..213.98 rows=5 width=20) (actual time=0.254..4.762 rows=50 loops=1)
  Join Filter: (w.vehicle_id = f.id)
  Rows Removed by Join Filter: 144
  Buffers: shared hit=319
  ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=40) (actual time=0.048..0.439 rows=50 loops=1)
        Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
        Filter: (id = ANY ($1))
        Rows Removed by Filter: 450
        Heap Blocks: exact=7
        Buffers: shared hit=8
        ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.033..0.033 rows=500 loops=1)
              Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
              Buffers: shared hit=1
  ->  Materialize  (cost=5.93..6.08 rows=5 width=80) (actual time=0.002..0.002 rows=3 loops=50)
        Buffers: shared hit=2
        ->  Subquery Scan on w  (cost=5.93..6.06 rows=5 width=80) (actual time=0.098..0.102 rows=3 loops=1)
              Buffers: shared hit=2
              ->  HashAggregate  (cost=5.93..6.01 rows=5 width=80) (actual time=0.098..0.100 rows=3 loops=1)
                    Group Key: a.vehicle_id
                    Batches: 1  Memory Usage: 24kB
                    Buffers: shared hit=2
                    ->  Seq Scan on vehicle_away_periods a  (cost=0.00..5.88 rows=5 width=24) (actual time=0.021..0.083 rows=3 loops=1)
                          Filter: ((vehicle_id = ANY ($1)) AND (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid))
                          Rows Removed by Filter: 108
                          Buffers: shared hit=2
  SubPlan 1
    ->  Result  (cost=0.42..8.44 rows=1 width=0) (actual time=0.013..0.013 rows=1 loops=50)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
          Buffers: shared hit=151
          ->  Index Only Scan using uq_records_vehicle_day on records r  (cost=0.42..8.44 rows=1 width=0) (actual time=0.006..0.006 rows=1 loops=50)
                Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = f.joined_on))
                Heap Fetches: 0
                Buffers: shared hit=151
  SubPlan 2
    ->  Limit  (cost=0.42..8.49 rows=1 width=8) (actual time=0.067..0.067 rows=1 loops=47)
          Buffers: shared hit=151
          ->  Subquery Scan on g  (cost=0.42..8.49 rows=1 width=8) (actual time=0.067..0.067 rows=1 loops=47)
                Filter: ((g.following IS DISTINCT FROM g.next_day) AND (NOT COALESCE((w.spans @> g.next_day), false)) AND (g.next_day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                Rows Removed by Filter: 32
                Buffers: shared hit=151
                ->  WindowAgg  (cost=0.42..8.47 rows=1 width=12) (actual time=0.024..0.061 rows=33 loops=47)
                      Buffers: shared hit=151
                      ->  Result  (cost=0.42..8.45 rows=1 width=4) (actual time=0.021..0.033 rows=34 loops=47)
                            One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                            Buffers: shared hit=151
                            ->  Index Only Scan using uq_records_vehicle_day on records r_1  (cost=0.42..8.45 rows=1 width=4) (actual time=0.014..0.023 rows=34 loops=47)
                                  Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date >= f.joined_on) AND (business_date < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END))
                                  Heap Fetches: 0
                                  Buffers: shared hit=151
  SubPlan 3
    ->  Aggregate  (cost=16.67..16.68 rows=1 width=4) (actual time=0.003..0.003 rows=1 loops=47)
          Buffers: shared hit=7
          ->  Nested Loop Anti Join  (cost=0.42..16.67 rows=1 width=4) (actual time=0.003..0.003 rows=0 loops=47)
                Buffers: shared hit=7
                ->  Function Scan on unnest x  (cost=0.00..0.20 rows=1 width=4) (actual time=0.001..0.001 rows=0 loops=47)
                      Filter: ((day > f.joined_on) AND (day < CASE WHEN (f.left_on < $2) THEN f.left_on ELSE $2 END) AND (NOT (w.spans @> day)))
                ->  Result  (cost=0.42..8.44 rows=1 width=4) (actual time=0.014..0.014 rows=1 loops=2)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = f.organization_id)
                      Buffers: shared hit=7
                      ->  Index Only Scan using uq_records_vehicle_day on records r_2  (cost=0.42..8.44 rows=1 width=4) (actual time=0.009..0.009 rows=1 loops=2)
                            Index Cond: ((organization_id = f.organization_id) AND (vehicle_id = f.id) AND (business_date = x.day))
                            Heap Fetches: 0
                            Buffers: shared hit=7
```

### week, one vehicle a year back

Routine statement: 45.6 ms; 37 nested statements logged.

13.1 ms: `WITH days AS MATERIALIZED ( SELECT d AS fact, d.vehicle_id, d.day, d.active, d.target, d.counted, d.record_id, d.amount FROM revenue.vehicle_days(v_gr ...`

```text
Subquery Scan on t  (cost=176.23..177.00 rows=1 width=32) (actual time=13.091..13.101 rows=1 loops=1)
  Buffers: shared hit=49
  CTE days
    ->  Function Scan on vehicle_days d_1  (cost=0.25..10.25 rows=1000 width=228) (actual time=8.887..8.894 rows=7 loops=1)
          Buffers: shared hit=26
  CTE missing
    ->  Function Scan on earliest_missing m  (cost=0.25..10.25 rows=1000 width=20) (actual time=2.377..2.378 rows=1 loops=1)
          Buffers: shared hit=18
  InitPlan 3 (returns $4)
    ->  Aggregate  (cost=54.11..54.12 rows=1 width=32) (actual time=3.510..3.514 rows=1 loops=1)
          Buffers: shared hit=23
          ->  Sort  (cost=53.84..53.85 rows=1 width=104) (actual time=2.712..2.717 rows=1 loops=1)
                Sort Key: s.ord
                Sort Method: quicksort  Memory: 25kB
                Buffers: shared hit=23
                ->  Result  (cost=30.03..53.83 rows=1 width=104) (actual time=2.675..2.686 rows=1 loops=1)
                      One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                      Buffers: shared hit=23
                      ->  Hash Right Join  (cost=30.03..53.83 rows=1 width=104) (actual time=2.646..2.656 rows=1 loops=1)
                            Hash Cond: (m_1.vehicle_id = s.id)
                            Buffers: shared hit=23
                            ->  CTE Scan on missing m_1  (cost=0.00..20.00 rows=1000 width=20) (actual time=2.380..2.381 rows=1 loops=1)
                                  Buffers: shared hit=18
                            ->  Hash  (cost=30.01..30.01 rows=1 width=116) (actual time=0.231..0.234 rows=1 loops=1)
                                  Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                  Buffers: shared hit=5
                                  ->  Nested Loop  (cost=21.74..30.01 rows=1 width=116) (actual time=0.220..0.223 rows=1 loops=1)
                                        Buffers: shared hit=5
                                        ->  Nested Loop  (cost=21.61..29.82 rows=1 width=121) (actual time=0.209..0.212 rows=1 loops=1)
                                              Join Filter: (f.id = s.id)
                                              Buffers: shared hit=3
                                              ->  Merge Join  (cost=21.33..21.51 rows=1 width=72) (actual time=0.147..0.149 rows=1 loops=1)
                                                    Merge Cond: (s.id = d_2.vehicle_id)
                                                    ->  Sort  (cost=0.02..0.03 rows=1 width=24) (actual time=0.060..0.061 rows=1 loops=1)
                                                          Sort Key: s.id
                                                          Sort Method: quicksort  Memory: 25kB
                                                          ->  Function Scan on unnest s  (cost=0.00..0.01 rows=1 width=24) (actual time=0.039..0.040 rows=1 loops=1)
                                                    ->  GroupAggregate  (cost=21.31..21.41 rows=5 width=48) (actual time=0.072..0.073 rows=1 loops=1)
                                                          Group Key: d_2.vehicle_id
                                                          ->  Sort  (cost=21.31..21.32 rows=5 width=52) (actual time=0.051..0.052 rows=7 loops=1)
                                                                Sort Key: d_2.vehicle_id, d_2.day
                                                                Sort Method: quicksort  Memory: 25kB
                                                                ->  CTE Scan on days d_2  (cost=0.00..21.25 rows=5 width=52) (actual time=0.006..0.009 rows=7 loops=1)
                                                                      Filter: (vehicle_id = ANY ('{...}'::uuid[]))
                                              ->  Index Scan using pk_fleet_vehicles on fleet_vehicles f  (cost=0.28..8.29 rows=1 width=65) (actual time=0.053..0.053 rows=1 loops=1)
                                                    Index Cond: ((organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid) AND (id = d_2.vehicle_id))
                                                    Buffers: shared hit=3
                                        ->  Index Scan using pk_psv_companies on psv_companies c  (cost=0.14..0.18 rows=1 width=43) (actual time=0.006..0.006 rows=1 loops=1)
                                              Index Cond: ((organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid) AND (id = f.company_id))
                                              Buffers: shared hit=2
  InitPlan 4 (returns $5)
    ->  Aggregate  (cost=29.72..29.73 rows=1 width=32) (actual time=0.214..0.216 rows=1 loops=1)
          ->  Sort  (cost=26.15..26.17 rows=7 width=68) (actual time=0.069..0.072 rows=7 loops=1)
                Sort Key: dt.day
                Sort Method: quicksort  Memory: 25kB
                ->  Subquery Scan on dt  (cost=25.86..26.05 rows=7 width=68) (actual time=0.054..0.060 rows=7 loops=1)
                      ->  HashAggregate  (cost=25.86..25.98 rows=7 width=72) (actual time=0.053..0.058 rows=7 loops=1)
                            Group Key: n.offset_days
                            Batches: 1  Memory Usage: 24kB
                            ->  Hash Right Join  (cost=0.16..25.51 rows=35 width=74) (actual time=0.030..0.041 rows=7 loops=1)
                                  Hash Cond: (d_3.day = ('2025-10-06'::date + n.offset_days))
                                  ->  CTE Scan on days d_3  (cost=0.00..20.00 rows=1000 width=70) (actual time=0.001..0.003 rows=7 loops=1)
                                  ->  Hash  (cost=0.07..0.07 rows=7 width=4) (actual time=0.019..0.020 rows=7 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                        ->  Function Scan on generate_series n  (cost=0.00..0.07 rows=7 width=4) (actual time=0.014..0.014 rows=7 loops=1)
  InitPlan 5 (returns $6)
    ->  Subquery Scan on g  (cost=46.86..46.88 rows=1 width=32) (actual time=0.028..0.030 rows=1 loops=1)
          ->  Limit  (cost=46.86..46.86 rows=1 width=28) (actual time=0.024..0.026 rows=1 loops=1)
                ->  Sort  (cost=46.86..46.88 rows=5 width=28) (actual time=0.023..0.025 rows=1 loops=1)
                      Sort Key: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END)), g_1.ord
                      Sort Method: quicksort  Memory: 25kB
                      ->  Nested Loop Left Join  (cost=0.03..46.84 rows=5 width=28) (actual time=0.016..0.020 rows=1 loops=1)
                            Join Filter: (t_1.vehicle_id = g_1.id)
                            Filter: (COALESCE(m_2.earliest_missing, CASE WHEN (t_1.active AND (t_1.record_id IS NULL)) THEN '2026-10-09'::date ELSE NULL::date END) IS NOT NULL)
                            ->  Hash Right Join  (cost=0.03..23.82 rows=5 width=28) (actual time=0.012..0.016 rows=1 loops=1)
                                  Hash Cond: (m_2.vehicle_id = g_1.id)
                                  ->  CTE Scan on missing m_2  (cost=0.00..20.00 rows=1000 width=20) (actual time=0.000..0.001 rows=1 loops=1)
                                  ->  Hash  (cost=0.01..0.01 rows=1 width=24) (actual time=0.006..0.006 rows=1 loops=1)
                                        Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                        ->  Function Scan on unnest g_1  (cost=0.00..0.01 rows=1 width=24) (actual time=0.004..0.004 rows=1 loops=1)
                            ->  CTE Scan on days t_1  (cost=0.00..22.50 rows=5 width=33) (actual time=0.002..0.002 rows=0 loops=1)
                                  Filter: (day = '2026-10-09'::date)
                                  Rows Removed by Filter: 7
  ->  Aggregate  (cost=25.00..25.02 rows=1 width=64) (actual time=8.947..8.948 rows=1 loops=1)
        Buffers: shared hit=26
        ->  CTE Scan on days d  (cost=0.00..20.00 rows=1000 width=65) (actual time=8.896..8.911 rows=7 loops=1)
              Buffers: shared hit=26
```

6.4 ms: `SELECT tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view')`

```text
Result  (cost=0.00..0.26 rows=1 width=4) (actual time=6.439..6.439 rows=1 loops=1)
  Buffers: shared hit=10
```

5.5 ms: `SELECT coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name, c.id), '[]') FROM setup.psv_companies AS c WHERE c.organizat ...`

```text
Aggregate  (cost=177.11..177.12 rows=1 width=32) (actual time=5.528..5.535 rows=1 loops=1)
  Buffers: shared hit=16
  ->  Sort  (cost=177.08..177.09 rows=4 width=27) (actual time=5.440..5.448 rows=10 loops=1)
        Sort Key: c.name, c.id
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=16
        ->  Result  (cost=12.41..177.04 rows=4 width=27) (actual time=3.124..5.410 rows=10 loops=1)
              One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
              Buffers: shared hit=16
              ->  Hash Join  (cost=12.41..177.04 rows=4 width=27) (actual time=3.110..5.391 rows=10 loops=1)
                    Hash Cond: (c.id = (setup.visible_companies()))
                    Buffers: shared hit=16
                    ->  Index Scan using pk_psv_companies on psv_companies c  (cost=0.14..164.70 rows=7 width=27) (actual time=0.988..3.246 rows=10 loops=1)
                          Index Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                          Filter: (setup.company_active_on(id, '2026-10-09'::date) OR (hashed SubPlan 2))
                          Buffers: shared hit=12
                          SubPlan 2
                            ->  Hash Join  (cost=20.29..51.76 rows=227 width=32) (never executed)
                                  Hash Cond: (f.id = (setup.visible_vehicles()))
                                  ->  Bitmap Heap Scan on fleet_vehicles f  (cost=8.02..35.77 rows=454 width=48) (never executed)
                                        Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                        Filter: ((joined_on <= '2025-10-12'::date) AND ((left_on IS NULL) OR (left_on > '2025-10-06'::date)))
                                        ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (never executed)
                                              Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                  ->  Hash  (cost=9.77..9.77 rows=200 width=16) (never executed)
                                        ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (never executed)
                                              Group Key: setup.visible_vehicles()
                                              ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (never executed)
                                                    ->  Result  (cost=0.00..0.01 rows=1 width=0) (never executed)
                    ->  Hash  (cost=9.77..9.77 rows=200 width=16) (actual time=2.101..2.103 rows=10 loops=1)
                          Buckets: 1024  Batches: 1  Memory Usage: 9kB
                          Buffers: shared hit=4
                          ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (actual time=2.086..2.091 rows=10 loops=1)
                                Group Key: setup.visible_companies()
                                Batches: 1  Memory Usage: 40kB
                                Buffers: shared hit=4
                                ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (actual time=1.514..2.074 rows=10 loops=1)
                                      Buffers: shared hit=4
                                      ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
```

4.8 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=4.825..4.826 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.029..0.029 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.017..0.018 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

### dashboard, today

Routine statement: 42.0 ms; 16 nested statements logged.

24.8 ms: `SELECT coalesce(sum(v.revenue), 0) AS revenue, coalesce(sum(v.target), 0) AS target, coalesce(sum(v.recorded_today), 0) AS captured_today, coalesce(su ...`

```text
Aggregate  (cost=49.77..49.77 rows=1 width=200) (actual time=24.804..24.805 rows=1 loops=1)
  Buffers: shared hit=2822
  ->  HashAggregate  (cost=40.25..43.25 rows=200 width=120) (actual time=23.870..24.338 rows=490 loops=1)
        Group Key: d.vehicle_id
        Batches: 1  Memory Usage: 569kB
        Buffers: shared hit=2822
        ->  Function Scan on vehicle_days d  (cost=0.25..10.25 rows=1000 width=103) (actual time=22.927..22.967 rows=490 loops=1)
              Buffers: shared hit=2822
```

17.0 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=11.674..16.596 rows=490 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 149
  Buffers: shared hit=2814
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=9.870..10.943 rows=490 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 53
        Buffers: shared hit=1825
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=9.079..9.820 rows=490 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=1823
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=4.192..4.268 rows=490 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 51kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.090..3.902 rows=490 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.013..0.018 rows=1 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.074..3.632 rows=490 loops=1)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.071..3.241 rows=490 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 10
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.051..0.052 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=4.876..4.917 rows=344 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 54kB
                    Buffers: shared hit=1815
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.322..4.586 rows=344 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 1313
                          Buffers: shared hit=1815
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.290..3.718 rows=344 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=1814
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.001 rows=4 loops=344)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.016..0.018 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.787..0.796 rows=55 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.065..0.743 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=1.797..4.297 rows=639 loops=1)
        Buffers: shared hit=989
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=1.789..3.923 rows=639 loops=1)
              Buffers: shared hit=989
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=1.775..2.477 rows=639 loops=1)
                    Buffers: shared hit=989
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=1.770..2.213 rows=639 loops=1)
                          Buffers: shared hit=989
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=1.769..1.865 rows=639 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 59kB
                                Buffers: shared hit=989
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=1.298..1.487 rows=639 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=989
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=1.285..1.285 rows=639 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=980
```

5.1 ms: `SELECT coalesce(array_agg(f.id), '{}') FROM setup.fleet_vehicles AS f WHERE f.organization_id = p_organization_id AND f.id IN (SELECT setup.visible_ve ...`

```text
Aggregate  (cost=47.68..47.69 rows=1 width=32) (actual time=5.047..5.050 rows=1 loops=1)
  Buffers: shared hit=19
  ->  Result  (cost=20.30..47.06 rows=245 width=16) (actual time=4.383..4.910 rows=490 loops=1)
        One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
        Buffers: shared hit=19
        ->  Hash Join  (cost=20.30..47.06 rows=245 width=16) (actual time=4.372..4.830 rows=490 loops=1)
              Hash Cond: (f.id = (setup.visible_vehicles()))
              Buffers: shared hit=19
              ->  Bitmap Heap Scan on fleet_vehicles f  (cost=8.02..30.77 rows=490 width=16) (actual time=0.055..0.287 rows=490 loops=1)
                    Recheck Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                    Filter: ((joined_on <= '2026-10-09'::date) AND ((left_on IS NULL) OR (left_on > '2026-10-09'::date)))
                    Rows Removed by Filter: 10
                    Heap Blocks: exact=7
                    Buffers: shared hit=8
                    ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.90 rows=500 width=0) (actual time=0.044..0.045 rows=500 loops=1)
                          Index Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                          Buffers: shared hit=1
              ->  Hash  (cost=9.77..9.77 rows=200 width=16) (actual time=4.310..4.311 rows=500 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 32kB
                    Buffers: shared hit=11
                    ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (actual time=4.065..4.167 rows=500 loops=1)
                          Group Key: setup.visible_vehicles()
                          Batches: 1  Memory Usage: 89kB
                          Buffers: shared hit=11
                          ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (actual time=1.811..3.779 rows=500 loops=1)
                                Buffers: shared hit=11
                                ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.000..0.001 rows=1 loops=1)
```

5.0 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=5.019..5.021 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.019..0.020 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.011..0.012 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

### dashboard, week

Routine statement: 65.7 ms; 18 nested statements logged.

52.2 ms: `SELECT coalesce(sum(v.revenue), 0) AS revenue, coalesce(sum(v.target), 0) AS target, coalesce(sum(v.recorded_today), 0) AS captured_today, coalesce(su ...`

```text
Aggregate  (cost=49.77..49.77 rows=1 width=200) (actual time=52.203..52.205 rows=1 loops=1)
  Buffers: shared hit=2999
  ->  HashAggregate  (cost=40.25..43.25 rows=200 width=120) (actual time=50.686..51.471 rows=490 loops=1)
        Group Key: d.vehicle_id
        Batches: 1  Memory Usage: 569kB
        Buffers: shared hit=2999
        ->  Function Scan on vehicle_days d  (cost=0.25..10.25 rows=1000 width=103) (actual time=39.119..39.573 rows=2450 loops=1)
              Buffers: shared hit=2999
```

34.4 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=18.586..32.394 rows=2450 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 745
  Buffers: shared hit=2991
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=16.562..22.148 rows=2450 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 265
        Buffers: shared hit=2002
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=15.790..20.078 rows=2450 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=2000
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=4.852..5.242 rows=2450 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 230kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.068..2.570 rows=2450 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.012..0.017 rows=5 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.011..0.398 rows=490 loops=5)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.052..1.583 rows=490 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 10
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.039..0.039 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=10.926..11.171 rows=2234 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 289kB
                    Buffers: shared hit=1992
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.362..8.825 rows=2234 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 8555
                          Buffers: shared hit=1992
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.293..4.568 rows=2234 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=1991
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.000 rows=4 loops=2234)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.030..0.032 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.769..0.799 rows=263 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.043..0.733 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=2.009..4.879 rows=3191 loops=1)
        Buffers: shared hit=989
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=2.003..4.163 rows=639 loops=1)
              Buffers: shared hit=989
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=1.983..2.648 rows=639 loops=1)
                    Buffers: shared hit=989
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=1.981..2.434 rows=639 loops=1)
                          Buffers: shared hit=989
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=1.978..2.101 rows=639 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 59kB
                                Buffers: shared hit=989
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=1.322..1.584 rows=639 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=989
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=1.310..1.310 rows=639 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=980
```

4.5 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=4.536..4.537 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.022..0.023 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.013..0.013 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

4.0 ms: `SELECT coalesce(array_agg(f.id), '{}') FROM setup.fleet_vehicles AS f WHERE f.organization_id = p_organization_id AND f.id IN (SELECT setup.visible_ve ...`

```text
Aggregate  (cost=47.68..47.69 rows=1 width=32) (actual time=4.026..4.029 rows=1 loops=1)
  Buffers: shared hit=19
  ->  Result  (cost=20.30..47.06 rows=245 width=16) (actual time=3.582..3.937 rows=490 loops=1)
        One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
        Buffers: shared hit=19
        ->  Hash Join  (cost=20.30..47.06 rows=245 width=16) (actual time=3.575..3.887 rows=490 loops=1)
              Hash Cond: (f.id = (setup.visible_vehicles()))
              Buffers: shared hit=19
              ->  Bitmap Heap Scan on fleet_vehicles f  (cost=8.02..30.77 rows=490 width=16) (actual time=0.036..0.202 rows=490 loops=1)
                    Recheck Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                    Filter: ((joined_on <= '2026-10-09'::date) AND ((left_on IS NULL) OR (left_on > '2026-10-05'::date)))
                    Rows Removed by Filter: 10
                    Heap Blocks: exact=7
                    Buffers: shared hit=8
                    ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.90 rows=500 width=0) (actual time=0.028..0.029 rows=500 loops=1)
                          Index Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                          Buffers: shared hit=1
              ->  Hash  (cost=9.77..9.77 rows=200 width=16) (actual time=3.533..3.534 rows=500 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 32kB
                    Buffers: shared hit=11
                    ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (actual time=3.345..3.421 rows=500 loops=1)
                          Group Key: setup.visible_vehicles()
                          Batches: 1  Memory Usage: 89kB
                          Buffers: shared hit=11
                          ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (actual time=1.253..3.065 rows=500 loops=1)
                                Buffers: shared hit=11
                                ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.000..0.001 rows=1 loops=1)
```

### dashboard, month

Routine statement: 100.0 ms; 16 nested statements logged.

82.2 ms: `SELECT coalesce(sum(v.revenue), 0) AS revenue, coalesce(sum(v.target), 0) AS target, coalesce(sum(v.recorded_today), 0) AS captured_today, coalesce(su ...`

```text
Aggregate  (cost=49.77..49.77 rows=1 width=200) (actual time=82.164..82.165 rows=1 loops=1)
  Buffers: shared hit=3031
  ->  HashAggregate  (cost=40.25..43.25 rows=200 width=120) (actual time=80.588..81.344 rows=490 loops=1)
        Group Key: d.vehicle_id
        Batches: 1  Memory Usage: 569kB
        Buffers: shared hit=3031
        ->  Function Scan on vehicle_days d  (cost=0.25..10.25 rows=1000 width=103) (actual time=70.691..71.348 rows=4410 loops=1)
              Buffers: shared hit=3031
```

65.2 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=33.600..61.092 rows=4410 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 1341
  Buffers: shared hit=3023
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=31.498..41.863 rows=4410 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 477
        Buffers: shared hit=2034
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=30.534..38.219 rows=4410 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=2032
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=10.577..11.414 rows=4410 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 434kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.069..4.125 rows=4410 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.011..0.018 rows=9 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.006..0.268 rows=490 loops=9)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.054..1.636 rows=490 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 10
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.041..0.041 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=19.945..20.465 rows=4139 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 550kB
                    Buffers: shared hit=2024
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.368..15.635 rows=4139 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 15872
                          Buffers: shared hit=2024
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.316..6.511 rows=4139 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=2023
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.000 rows=4 loops=4139)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.032..0.034 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.959..1.008 rows=471 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.042..0.903 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=2.094..5.763 rows=5743 loops=1)
        Buffers: shared hit=989
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=2.088..4.690 rows=639 loops=1)
              Buffers: shared hit=989
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=2.065..2.867 rows=639 loops=1)
                    Buffers: shared hit=989
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=2.063..2.605 rows=639 loops=1)
                          Buffers: shared hit=989
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=2.062..2.211 rows=639 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 59kB
                                Buffers: shared hit=989
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=1.603..1.784 rows=639 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=989
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=1.587..1.588 rows=639 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=980
```

6.8 ms: `SELECT coalesce(array_agg(f.id), '{}') FROM setup.fleet_vehicles AS f WHERE f.organization_id = p_organization_id AND f.id IN (SELECT setup.visible_ve ...`

```text
Aggregate  (cost=47.68..47.69 rows=1 width=32) (actual time=6.745..6.748 rows=1 loops=1)
  Buffers: shared hit=19
  ->  Result  (cost=20.30..47.06 rows=245 width=16) (actual time=5.984..6.590 rows=490 loops=1)
        One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
        Buffers: shared hit=19
        ->  Hash Join  (cost=20.30..47.06 rows=245 width=16) (actual time=5.968..6.487 rows=490 loops=1)
              Hash Cond: (f.id = (setup.visible_vehicles()))
              Buffers: shared hit=19
              ->  Bitmap Heap Scan on fleet_vehicles f  (cost=8.02..30.77 rows=490 width=16) (actual time=0.065..0.324 rows=490 loops=1)
                    Recheck Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                    Filter: ((joined_on <= '2026-10-09'::date) AND ((left_on IS NULL) OR (left_on > '2026-10-01'::date)))
                    Rows Removed by Filter: 10
                    Heap Blocks: exact=7
                    Buffers: shared hit=8
                    ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.90 rows=500 width=0) (actual time=0.051..0.051 rows=500 loops=1)
                          Index Cond: (organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
                          Buffers: shared hit=1
              ->  Hash  (cost=9.77..9.77 rows=200 width=16) (actual time=5.894..5.895 rows=500 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 32kB
                    Buffers: shared hit=11
                    ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (actual time=5.618..5.729 rows=500 loops=1)
                          Group Key: setup.visible_vehicles()
                          Batches: 1  Memory Usage: 89kB
                          Buffers: shared hit=11
                          ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (actual time=2.673..5.244 rows=500 loops=1)
                                Buffers: shared hit=11
                                ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.000..0.001 rows=1 loops=1)
```

4.9 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=4.915..4.916 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.030..0.030 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.019..0.019 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

### dashboard, month, one company

Routine statement: 28.4 ms; 16 nested statements logged.

11.9 ms: `SELECT coalesce(sum(v.revenue), 0) AS revenue, coalesce(sum(v.target), 0) AS target, coalesce(sum(v.recorded_today), 0) AS captured_today, coalesce(su ...`

```text
Aggregate  (cost=49.77..49.77 rows=1 width=200) (actual time=11.938..11.939 rows=1 loops=1)
  Buffers: shared hit=341
  ->  HashAggregate  (cost=40.25..43.25 rows=200 width=120) (actual time=11.884..11.909 rows=50 loops=1)
        Group Key: d.vehicle_id
        Batches: 1  Memory Usage: 96kB
        Buffers: shared hit=341
        ->  Function Scan on vehicle_days d  (cost=0.25..10.25 rows=1000 width=103) (actual time=11.622..11.643 rows=450 loops=1)
              Buffers: shared hit=341
```

7.1 ms: `WITH vehicles AS ( SELECT f.id, f.joined_on, f.left_on FROM setup.fleet_vehicles AS f WHERE f.organization_id = tenancy.current_organization() AND f.i ...`

```text
Merge Left Join  (cost=547.39..817.19 rows=5000 width=153) (actual time=5.865..6.885 rows=450 loops=1)
  Merge Cond: (f.id = t.vehicle_id)
  Join Filter: ((($2 + n.offset_days) >= t.effective_from) AND (((lead(t.effective_from) OVER (?)) IS NULL) OR (($2 + n.offset_days) < (lead(t.effective_from) OVER (?)))))
  Rows Removed by Join Filter: 153
  Buffers: shared hit=333
  ->  Merge Left Join  (cost=506.45..575.91 rows=5000 width=115) (actual time=5.562..6.009 rows=450 loops=1)
        Merge Cond: (f.id = a.vehicle_id)
        Join Filter: ((($2 + n.offset_days) >= a.left_on) AND (($2 + n.offset_days) < a.returned_on))
        Rows Removed by Join Filter: 27
        Buffers: shared hit=224
        ->  Merge Left Join  (cost=500.36..550.47 rows=5000 width=99) (actual time=4.654..4.985 rows=450 loops=1)
              Merge Cond: ((f.id = r.vehicle_id) AND ((($2 + n.offset_days)) = r.business_date))
              Buffers: shared hit=222
              ->  Sort  (cost=419.12..431.62 rows=5000 width=28) (actual time=1.782..1.816 rows=450 loops=1)
                    Sort Key: f.id, (($2 + n.offset_days))
                    Sort Method: quicksort  Memory: 49kB
                    Buffers: shared hit=8
                    ->  Nested Loop  (cost=7.92..111.93 rows=5000 width=28) (actual time=0.126..1.212 rows=450 loops=1)
                          Buffers: shared hit=8
                          ->  Function Scan on generate_series n  (cost=0.01..10.01 rows=1000 width=4) (actual time=0.019..0.038 rows=9 loops=1)
                          ->  Materialize  (cost=7.91..39.44 rows=5 width=24) (actual time=0.012..0.108 rows=50 loops=9)
                                Buffers: shared hit=8
                                ->  Bitmap Heap Scan on fleet_vehicles f  (cost=7.91..39.41 rows=5 width=24) (actual time=0.099..0.869 rows=50 loops=1)
                                      Recheck Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                      Filter: (id = ANY ($1))
                                      Rows Removed by Filter: 450
                                      Heap Blocks: exact=7
                                      Buffers: shared hit=8
                                      ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..7.91 rows=500 width=0) (actual time=0.068..0.068 rows=500 loops=1)
                                            Index Cond: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                            Buffers: shared hit=1
              ->  Sort  (cost=81.24..81.26 rows=10 width=91) (actual time=2.836..2.861 rows=419 loops=1)
                    Sort Key: r.vehicle_id, r.business_date
                    Sort Method: quicksort  Memory: 61kB
                    Buffers: shared hit=214
                    ->  Nested Loop Left Join  (cost=0.43..81.07 rows=10 width=91) (actual time=0.353..2.194 rows=419 loops=1)
                          Join Filter: (l.code = r.reason)
                          Rows Removed by Join Filter: 1614
                          Buffers: shared hit=214
                          ->  Index Scan using uq_records_vehicle_day on records r  (cost=0.43..79.42 rows=10 width=84) (actual time=0.185..1.104 rows=419 loops=1)
                                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (business_date >= $2) AND (business_date <= $3))
                                Buffers: shared hit=213
                          ->  Materialize  (cost=0.00..1.06 rows=4 width=9) (actual time=0.000..0.001 rows=4 loops=419)
                                Buffers: shared hit=1
                                ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.110..0.114 rows=4 loops=1)
                                      Buffers: shared hit=1
        ->  Sort  (cost=6.09..6.22 rows=55 width=24) (actual time=0.899..0.904 rows=76 loops=1)
              Sort Key: a.vehicle_id
              Sort Method: quicksort  Memory: 27kB
              Buffers: shared hit=2
              ->  Seq Scan on vehicle_away_periods a  (cost=0.00..4.50 rows=55 width=24) (actual time=0.154..0.808 rows=55 loops=1)
                    Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                    Rows Removed by Filter: 56
                    Buffers: shared hit=2
  ->  Materialize  (cost=40.94..41.03 rows=2 width=29) (actual time=0.296..0.452 rows=595 loops=1)
        Buffers: shared hit=109
        ->  WindowAgg  (cost=40.94..41.01 rows=2 width=29) (actual time=0.284..0.390 rows=67 loops=1)
              Buffers: shared hit=109
              ->  Subquery Scan on t  (cost=40.94..40.97 rows=2 width=25) (actual time=0.270..0.302 rows=67 loops=1)
                    Buffers: shared hit=109
                    ->  Unique  (cost=40.94..40.95 rows=2 width=29) (actual time=0.269..0.290 rows=67 loops=1)
                          Buffers: shared hit=109
                          ->  Sort  (cost=40.94..40.94 rows=2 width=29) (actual time=0.267..0.272 rows=67 loops=1)
                                Sort Key: t_1.vehicle_id, t_1.effective_from, t_1.revision DESC
                                Sort Method: quicksort  Memory: 28kB
                                Buffers: shared hit=109
                                ->  Bitmap Heap Scan on vehicle_targets t_1  (cost=34.91..40.93 rows=2 width=29) (actual time=0.190..0.225 rows=67 loops=1)
                                      Recheck Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                      Heap Blocks: exact=9
                                      Buffers: shared hit=109
                                      ->  Bitmap Index Scan on ix_vehicle_targets_in_force  (cost=0.00..34.91 rows=2 width=0) (actual time=0.175..0.175 rows=67 loops=1)
                                            Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (vehicle_id = ANY ($1)) AND (effective_from <= $3))
                                            Buffers: shared hit=100
```

6.9 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=6.879..6.880 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.040..0.041 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.023..0.023 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

5.0 ms: `SELECT coalesce(array_agg(f.id), '{}') FROM setup.fleet_vehicles AS f WHERE f.organization_id = p_organization_id AND f.id IN (SELECT setup.visible_ve ...`

```text
Aggregate  (cost=30.65..30.66 rows=1 width=32) (actual time=4.977..4.979 rows=1 loops=1)
  Buffers: shared hit=19
  ->  Result  (cost=26.98..30.62 rows=12 width=16) (actual time=4.717..4.958 rows=50 loops=1)
        One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid)
        Buffers: shared hit=19
        ->  Hash Join  (cost=26.98..30.62 rows=12 width=16) (actual time=4.705..4.938 rows=50 loops=1)
              Hash Cond: ((setup.visible_vehicles()) = f.id)
              Buffers: shared hit=19
              ->  HashAggregate  (cost=7.77..9.77 rows=200 width=16) (actual time=4.591..4.735 rows=500 loops=1)
                    Group Key: setup.visible_vehicles()
                    Batches: 1  Memory Usage: 89kB
                    Buffers: shared hit=11
                    ->  ProjectSet  (cost=0.00..5.27 rows=1000 width=16) (actual time=2.357..4.307 rows=500 loops=1)
                          Buffers: shared hit=11
                          ->  Result  (cost=0.00..0.01 rows=1 width=0) (actual time=0.001..0.001 rows=1 loops=1)
              ->  Hash  (cost=18.91..18.91 rows=24 width=16) (actual time=0.095..0.096 rows=50 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 11kB
                    Buffers: shared hit=8
                    ->  Bitmap Heap Scan on fleet_vehicles f  (cost=4.41..18.91 rows=24 width=16) (actual time=0.035..0.073 rows=50 loops=1)
                          Recheck Cond: ((organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid) AND (company_id = '81234bc7-a5a1-41c6-bcad-6c305c1c2923'::uuid))
                          Filter: ((joined_on <= '2026-10-09'::date) AND ((left_on IS NULL) OR (left_on > '2026-10-01'::date)))
                          Heap Blocks: exact=7
                          Buffers: shared hit=8
                          ->  Bitmap Index Scan on ix_fleet_vehicles_company  (cost=0.00..4.40 rows=25 width=0) (actual time=0.017..0.017 rows=50 loops=1)
                                Index Cond: ((organization_id = '234c6f8a-4030-416e-9fa5-eeb91be118fb'::uuid) AND (company_id = '81234bc7-a5a1-41c6-bcad-6c305c1c2923'::uuid))
                                Buffers: shared hit=1
```

### capture, update (version 1 -> 2)

Routine statement: 31.2 ms; 37 nested statements logged.

8.0 ms: `SELECT tenancy.record_change( 'revenue', v_id, p_vehicle_id, v_before, v_after, CASE WHEN NOT v_exists AND v_reason IS NULL THEN 'Recorded revenue' || ...`

```text
Result  (cost=0.00..0.26 rows=1 width=8) (actual time=7.984..7.984 rows=1 loops=1)
  Buffers: shared hit=331 dirtied=1
```

5.0 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=5.036..5.037 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.022..0.023 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.014..0.014 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

2.3 ms: `SELECT tenancy.compact_json(coalesce( ( SELECT json_build_object( 'Id', r.id, 'VehicleId', r.vehicle_id, 'BusinessDate', r.business_date, 'Amount', tr ...`

```text
Result  (cost=10.05..10.31 rows=1 width=32) (actual time=2.293..2.294 rows=1 loops=1)
  Buffers: shared hit=84
  InitPlan 1 (returns $0)
    ->  Nested Loop Left Join  (cost=0.43..10.05 rows=1 width=32) (actual time=1.292..1.296 rows=1 loops=1)
          Join Filter: (l.code = r.reason)
          Rows Removed by Join Filter: 4
          Buffers: shared hit=25
          ->  Index Scan using pk_records on records r  (cost=0.43..8.45 rows=1 width=132) (actual time=0.037..0.040 rows=1 loops=1)
                Index Cond: ((organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid) AND (id = $1))
                Buffers: shared hit=4
          ->  Seq Scan on no_earnings_reasons l  (cost=0.00..1.04 rows=4 width=9) (actual time=0.012..0.013 rows=4 loops=1)
                Buffers: shared hit=1
```

### capture, new record

Routine statement: 29.3 ms; 37 nested statements logged.

9.5 ms: `INSERT INTO revenue.records ( organization_id, vehicle_id, business_date, amount, reason, note, captured_at, captured_by, updated_at, updated_by ) VAL ...`

```text
Insert on records  (cost=0.00..0.01 rows=1 width=161) (actual time=7.283..7.286 rows=1 loops=1)
  Buffers: shared hit=10 read=1 dirtied=1
  ->  Result  (cost=0.00..0.01 rows=1 width=161) (actual time=0.021..0.022 rows=1 loops=1)
```

6.2 ms: `SELECT CASE WHEN EXISTS ( SELECT 1 FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id AND m.active )  ...`

```text
Result  (cost=1.06..1.32 rows=1 width=32) (actual time=6.156..6.157 rows=1 loops=1)
  Buffers: shared hit=9
  InitPlan 1 (returns $0)
    ->  Result  (cost=0.01..1.06 rows=1 width=0) (actual time=0.031..0.032 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=0) (actual time=0.019..0.019 rows=1 loops=1)
                Filter: (active AND (organization_id = $1) AND (user_id = $2))
                Buffers: shared hit=1
```

2.9 ms: `SELECT tenancy.record_change( 'revenue', v_id, p_vehicle_id, v_before, v_after, CASE WHEN NOT v_exists AND v_reason IS NULL THEN 'Recorded revenue' || ...`

```text
Result  (cost=0.00..0.26 rows=1 width=8) (actual time=2.861..2.861 rows=1 loops=1)
  Buffers: shared hit=42 dirtied=1
```

2.0 ms: `WITH RECURSIVE member AS ( SELECT m.organization_id, m.user_id FROM tenancy.memberships AS m WHERE m.organization_id = p_organization_id AND m.user_id ...`

```text
Aggregate  (cost=746.88..746.89 rows=1 width=32) (actual time=2.008..2.023 rows=1 loops=1)
  Buffers: shared hit=8
  CTE member
    ->  Result  (cost=0.01..1.06 rows=1 width=32) (actual time=0.025..0.027 rows=1 loops=1)
          One-Time Filter: ((NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid = $1)
          Buffers: shared hit=1
          ->  Seq Scan on memberships m  (cost=0.01..1.06 rows=1 width=32) (actual time=0.017..0.018 rows=1 loops=1)
                Filter: ((organization_id = $1) AND (user_id = $2))
                Rows Removed by Filter: 2
                Buffers: shared hit=1
  CTE overrides
    ->  Nested Loop  (cost=0.00..1.09 rows=1 width=14) (actual time=0.034..0.043 rows=1 loops=1)
          Join Filter: (o.user_id = member.user_id)
          Buffers: shared hit=1
          ->  CTE Scan on member  (cost=0.00..0.03 rows=1 width=32) (actual time=0.008..0.008 rows=1 loops=1)
                Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
          ->  Seq Scan on permission_overrides o  (cost=0.00..1.04 rows=1 width=46) (actual time=0.025..0.032 rows=1 loops=1)
                Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                Rows Removed by Filter: 1
                Buffers: shared hit=1
  CTE expanded
    ->  Recursive Union  (cost=4.40..29.45 rows=222 width=32) (actual time=1.270..1.399 rows=40 loops=1)
          Buffers: shared hit=6
          ->  Unique  (cost=4.40..4.41 rows=2 width=32) (actual time=1.268..1.296 rows=40 loops=1)
                Buffers: shared hit=5
                ->  Sort  (cost=4.40..4.40 rows=2 width=32) (actual time=1.266..1.275 rows=40 loops=1)
                      Sort Key: d.permission
                      Sort Method: quicksort  Memory: 26kB
                      Buffers: shared hit=5
                      ->  Append  (cost=1.19..4.39 rows=2 width=32) (actual time=0.154..1.229 rows=40 loops=1)
                            Buffers: shared hit=5
                            ->  Nested Loop  (cost=1.19..4.36 rows=1 width=14) (actual time=0.153..1.169 rows=39 loops=1)
                                  Join Filter: (pr.user_id = member_1.user_id)
                                  Buffers: shared hit=4
                                  ->  Nested Loop  (cost=1.19..4.31 rows=1 width=46) (actual time=0.119..0.818 rows=39 loops=1)
                                        Join Filter: (r.id = pr.role_id)
                                        Rows Removed by Join Filter: 40
                                        Buffers: shared hit=3
                                        ->  Seq Scan on person_roles pr  (cost=0.00..1.04 rows=1 width=48) (actual time=0.036..0.044 rows=1 loops=1)
                                              Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                              Rows Removed by Filter: 1
                                              Buffers: shared hit=1
                                        ->  Hash Join  (cost=1.19..3.22 rows=4 width=46) (actual time=0.081..0.746 rows=79 loops=1)
                                              Hash Cond: (lower(d.role_name) = lower(r.name))
                                              Buffers: shared hit=2
                                              ->  Seq Scan on role_defaults d  (cost=0.00..1.79 rows=79 width=23) (actual time=0.014..0.504 rows=79 loops=1)
                                                    Buffers: shared hit=1
                                              ->  Hash  (cost=1.14..1.14 rows=4 width=43) (actual time=0.059..0.060 rows=4 loops=1)
                                                    Buckets: 1024  Batches: 1  Memory Usage: 9kB
                                                    Buffers: shared hit=1
                                                    ->  Seq Scan on roles r  (cost=0.00..1.14 rows=4 width=43) (actual time=0.017..0.048 rows=4 loops=1)
                                                          Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                                          Rows Removed by Filter: 2
                                                          Buffers: shared hit=1
                                  ->  CTE Scan on member member_1  (cost=0.00..0.03 rows=1 width=32) (actual time=0.008..0.008 rows=1 loops=39)
                                        Filter: (organization_id = (NULLIF(current_setting('xcode.organization_id'::text, true), ''::text))::uuid)
                                        Buffers: shared hit=1
                            ->  CTE Scan on overrides  (cost=0.00..0.02 rows=1 width=32) (actual time=0.044..0.052 rows=1 loops=1)
                                  Filter: granted
                                  Buffers: shared hit=1
          ->  Hash Join  (cost=0.65..2.28 rows=22 width=14) (actual time=0.050..0.072 rows=30 loops=1)
                Hash Cond: (dep.permission = expanded.permission)
                Buffers: shared hit=1
                ->  Seq Scan on permission_dependencies dep  (cost=0.00..1.30 rows=30 width=28) (actual time=0.012..0.015 rows=30 loops=1)
                      Buffers: shared hit=1
                ->  Hash  (cost=0.40..0.40 rows=20 width=32) (actual time=0.027..0.027 rows=40 loops=1)
                      Buckets: 1024  Batches: 1  Memory Usage: 10kB
                      ->  WorkTable Scan on expanded  (cost=0.00..0.40 rows=20 width=32) (actual time=0.001..0.004 rows=40 loops=1)
  CTE held
    ->  HashSetOp Except  (cost=0.00..8.36 rows=200 width=36) (actual time=1.448..1.455 rows=40 loops=1)
          Buffers: shared hit=6
          ->  Append  (cost=0.00..7.81 rows=223 width=36) (actual time=1.275..1.431 rows=40 loops=1)
                Buffers: shared hit=6
                ->  Subquery Scan on "*SELECT* 1_1"  (cost=0.00..6.66 rows=222 width=36) (actual time=1.273..1.422 rows=40 loops=1)
                      Buffers: shared hit=6
                      ->  CTE Scan on expanded expanded_1  (cost=0.00..4.44 rows=222 width=32) (actual time=1.272..1.409 rows=40 loops=1)
                            Buffers: shared hit=6
                ->  Subquery Scan on "*SELECT* 2_1"  (cost=0.00..0.03 rows=1 width=36) (actual time=0.002..0.002 rows=0 loops=1)
                      ->  CTE Scan on overrides overrides_1  (cost=0.00..0.02 rows=1 width=32) (actual time=0.001..0.001 rows=0 loops=1)
                            Filter: (NOT granted)
                            Rows Removed by Filter: 1
  CTE closure
    ->  Recursive Union  (cost=0.00..607.75 rows=3200 width=64) (actual time=0.003..0.183 rows=75 loops=1)
          Buffers: shared hit=1
          ->  CTE Scan on held held_1  (cost=0.00..4.00 rows=200 width=64) (actual time=0.001..0.014 rows=40 loops=1)
          ->  Hash Join  (cost=1.68..57.17 rows=300 width=46) (actual time=0.023..0.034 rows=12 loops=3)
                Hash Cond: (closure_1.permission = dep_1.permission)
                Buffers: shared hit=1
                ->  WorkTable Scan on closure closure_1  (cost=0.00..40.00 rows=2000 width=64) (actual time=0.000..0.003 rows=25 loops=3)
                ->  Hash  (cost=1.30..1.30 rows=30 width=28) (actual time=0.051..0.051 rows=30 loops=1)
                      Buckets: 1024  Batches: 1  Memory Usage: 10kB
                      Buffers: shared hit=1
                      ->  Seq Scan on permission_dependencies dep_1  (cost=0.00..1.30 rows=30 width=28) (actual time=0.022..0.030 rows=30 loops=1)
                            Buffers: shared hit=1
  ->  Sort  (cost=99.07..99.12 rows=20 width=19) (actual time=1.987..1.993 rows=40 loops=1)
        Sort Key: p.group_order, p.item_order
        Sort Method: quicksort  Memory: 26kB
        Buffers: shared hit=8
        ->  Hash Right Anti Join  (cost=11.44..98.64 rows=20 width=19) (actual time=1.943..1.959 rows=40 loops=1)
              Hash Cond: (closure.root = held.permission)
              Buffers: shared hit=8
              ->  CTE Scan on closure  (cost=4.50..76.50 rows=1600 width=32) (actual time=0.372..0.373 rows=0 loops=1)
                    Filter: (NOT (hashed SubPlan 6))
                    Rows Removed by Filter: 75
                    Buffers: shared hit=1
                    SubPlan 6
                      ->  CTE Scan on held held_again  (cost=0.00..4.00 rows=200 width=32) (actual time=0.001..0.008 rows=40 loops=1)
              ->  Hash  (cost=6.44..6.44 rows=40 width=51) (actual time=1.564..1.566 rows=40 loops=1)
                    Buckets: 1024  Batches: 1  Memory Usage: 11kB
                    Buffers: shared hit=7
                    ->  Hash Join  (cost=1.90..6.44 rows=40 width=51) (actual time=1.499..1.543 rows=40 loops=1)
                          Hash Cond: (held.permission = p.key)
                          Buffers: shared hit=7
                          ->  CTE Scan on held  (cost=0.00..4.00 rows=200 width=32) (actual time=1.451..1.471 rows=40 loops=1)
                                Buffers: shared hit=6
                          ->  Hash  (cost=1.40..1.40 rows=40 width=19) (actual time=0.040..0.041 rows=40 loops=1)
                                Buckets: 1024  Batches: 1  Memory Usage: 11kB
                                Buffers: shared hit=1
                                ->  Seq Scan on permissions p  (cost=0.00..1.40 rows=40 width=19) (actual time=0.013..0.023 rows=40 loops=1)
                                      Buffers: shared hit=1
```
