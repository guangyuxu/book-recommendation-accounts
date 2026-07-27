"""End-to-end journeys against a REAL ephemeral Postgres. Opt-in: `make integration`.

Unlike `tests/unit_tests` (which mirrors `src/accounts/`), this suite is organized by BUSINESS FLOW
-- one file per journey a real user takes -- because a journey crosses many modules by definition.
It is deliberately kept out of the blocking `make ci` gate: it needs the Postgres binaries on PATH
(pytest-postgresql spins up a throwaway cluster via initdb/pg_ctl) and it is slower. CI runs it as
its own job (see the `integration` job in `.github/workflows/ci.yml`).
"""
