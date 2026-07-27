"""Fast, offline unit tests. This tree MIRRORS `src/accounts/`.

One directory per source subpackage (`routers/` covers `src/accounts/routers/`, `db/` covers
`src/accounts/db/`), so a test's location tells you what it covers and a source package with no
mirror directory is a visible coverage gap. Filenames stay descriptive rather than strictly 1:1 with
module names -- several files may cover one module (`routers/test_auth.py` and
`routers/test_refresh.py` both drive `routers/auth.py`).

Two deliberate exceptions sit at this root because they span several top-level modules by nature:
  - `test_ops.py` -- health / readiness / error envelope / correlation id / settings parsing.
  - `test_transactions.py` -- the request-scoped DI session boundary (`container` + `providers`).

End-to-end journeys that cross many modules belong in `tests/integration_tests/` instead, where
files are named after the FLOW, not the module.
"""
