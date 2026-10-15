-- Operator-action audit and rate-limit windows in schema ops.

CREATE TABLE ops.operator_actions (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  operator text NOT NULL CHECK (char_length(operator) BETWEEN 1 AND 128),
  action text NOT NULL,
  target text,
  detail jsonb NOT NULL DEFAULT '{}',
  recorded_at timestamptz NOT NULL
);

CREATE INDEX operator_actions_recorded_at_idx ON ops.operator_actions (recorded_at);

-- Append-only by privilege: the executor may insert and read, never update or delete.
REVOKE UPDATE, DELETE ON ops.operator_actions FROM xcode_api_executor;

CREATE UNLOGGED TABLE ops.rate_limit_windows (
  key text NOT NULL,
  window_start timestamptz NOT NULL,
  count integer NOT NULL,
  PRIMARY KEY (key, window_start)
);
