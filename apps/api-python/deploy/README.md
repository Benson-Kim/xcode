# deploy/

Specification: `docs/08-operability.md` section 9. The operator's procedures are
`runbook.md`.

- `Dockerfile`: multi-stage, non-root (uid 10001), base image pinned by digest.
- The CI workflow is `.github/workflows/xcode-api.yml` in the repository root: `lint`,
  `typecheck`, `test`, `audit`, `db-verify` (a fresh database migrated, checked, seeded and
  checked again) and `image` (build, vulnerability scan, uid and read-only run, push on tags).
  Its actions are pinned by commit.

## Base image digest

Both stages use `python:3.13-slim-bookworm` pinned by the digest of its multi-platform index,
so a rebuild starts from a known image and the CI scan governs that image. To renew it, read
the digest from the registry (no Docker needed) and change both `FROM` lines and the table
together:

```
TOKEN=$(curl -s "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/python:pull" | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -sI -H "Authorization: Bearer $TOKEN" -H "Accept: application/vnd.oci.image.index.v1+json" https://registry-1.docker.io/v2/library/python/manifests/3.13-slim-bookworm | grep -i docker-content-digest
```

| Captured (UTC date) | Tag | Digest | How |
|---|---|---|---|
| 2026-10-12 | `python:3.13-slim-bookworm` | `sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641` | registry API, the command above (the authoring machine has no Docker) |

## Running the container

```
docker run --read-only --tmpfs /tmp --env-file <the platform's secret store, never a file in the image> \
  -p 127.0.0.1:5000:5000 <image> serve
```

- The root filesystem is read-only; `/tmp` is a tmpfs. The process writes nothing else
  (`PYTHONDONTWRITEBYTECODE=1`, logs on stdout).
- The image's `HEALTHCHECK` calls `/health/live` on port 5000; the platform's readiness probe
  calls `/health/ready` (503 until the startup checks pass, and whenever the database does not
  answer within 10 s).
- Migrations run as a one-off job with the owner URL before the replicas roll:
  `docker run --rm -e XCODE_ENV=production -e XCODE_MIGRATION_DATABASE_URL=... <image> db migrate`.

## Connection limits

`xcode_app` connection limit = replicas x `XCODE_DATABASE_POOL_MAX` + 4 (headroom for the
readiness probes and an operator's session). `xcode_operator` and `xcode_readonly` keep
`CONNECTION LIMIT 5`. The structure test only checks that a limit is set; the value per
environment is set with `ALTER ROLE xcode_app CONNECTION LIMIT <n>` as the owner of the roles.

| Environment | Replicas | Pool max | `xcode_app` limit |
|---|---|---|---|
| compose (local development) | 1 | 10 | 14 |
| staging | open (question 3) | | |
| production | open (question 3) | | |

## The cPanel account `priori`

The intended host is the shared cPanel account `priori` (`docs/08-operability.md` section 9),
not a container platform. None of the facts below has been measured on it yet, so nothing in
this file is proven for that host. Each row names the open question in
`docs/13-open-questions.md` and the command that answers it; record the output here with the
date.

| Fact | Question | Command (run in the account's terminal or over SSH) | Measured |
|---|---|---|---|
| PostgreSQL version | 39 | `psql -Atc "select version()"` and `ls /usr/pgsql-*/bin 2>/dev/null; rpm -qa \| grep -i postgresql` | not yet |
| The five roles can exist (`NOLOGIN`, no `BYPASSRLS`, connection limits, per-role settings) | 40 | as the cPanel database user: `psql -c "select rolcreaterole, rolsuper from pg_roles where rolname = current_user"`; then try `psql -v ON_ERROR_STOP=1 -f db/roles/010_roles.sql` in a scratch database | not yet |
| How an ASGI app runs with its lifespan | 41 | `ls ~/virtualenv 2>/dev/null; cloudlinux-selector get --json --interpreter python 2>/dev/null`; whether a long-running `xcode-api serve` is allowed (a managed process or cron `@reboot`) rather than Passenger's WSGI | not yet |
| Python versions offered | 42 | `ls /opt/alt/ \| grep python; /opt/alt/python313/bin/python3 --version` | not yet |
| Thread budget under load | 43 | `ps -L -u $(whoami) \| wc -l` before and while the API serves a load test; `cat /proc/$(pgrep -f "xcode-api serve")/status \| grep Threads` | not yet |
| Where secrets live | 44 | whether the account offers per-application environment variables outside the web root; `ls -la ~` for any `.env` beside the web | not yet |
| How a release is proven authentic | 45 | the installer's verification step (`ssh-keygen -Y verify` against a pinned public key, or none today) | not yet |

Until these are measured, the defaults of those questions stand: the database does not go on
a host where the roles cannot exist (40); the server must run the lifespan (41); one API
process with its threads counted (the event loop, the default executor of at most `cpu + 4`
threads, the PIN pool's 2, the mail queue task, the pool's workers) (43); a separate cPanel
account for the API and its database (44); signed releases (45).
