# xcode_api.cli

Composition root for the command line (`xcode-api`). Builds a container and calls use cases;
holds no rules. Every command records the operator in `ops.operator_actions`.

`serve`, `openapi` and `settings-check` validate the full `Settings`; the `db` and operator
commands load `CliSettings` (environment, their connection URL, operator name) and never the
API's own configuration.

See `docs/08-operability.md` section 8.
