# Book Recommendation Accounts

Identity provider + family/child CRUD for the book-recommendation platform. It owns
signup/login, **issues RS256 access tokens** (holds the private key), and is the **single writer**
of the family / member / child / reading-profile / policy tables.

Two faces:

- **External face** (user token, RS256): the frontend connects directly for signup/login and
  family management (`/auth/*`, `/family/*`, `/me`).
- **Internal face** (service token, agent-only): `/internal/*` — the agent calls these instead of
  writing the shared tables directly (see [ACCOUNTS_SPLIT_PLAN in the BFF repo](../book-recommendation-service/ACCOUNTS_SPLIT_PLAN.md)).
  This face must be bound to an internal network and never exposed publicly.

The BFF ([book-recommendation-service](../book-recommendation-service)) holds only the **public
key** and verifies tokens; it never signs. See [CLAUDE.md](./CLAUDE.md) for project rules.

## Quickstart

```bash
uv sync                          # install deps + create the venv
cp .env.example .env             # dev defaults (local sqlite is used by tests automatically)
make keygen                      # generate keys/private.pem + keys/public.pem (gitignored)
make init-db                     # create the schema + tables from the models (needs Postgres via BOOK_AGENT_DATABASE_URL)
make run                         # http://localhost:8001/docs
```

Verify by signing up (returns an access token; every other endpoint requires the `Bearer` token):
`curl -sX POST localhost:8001/auth/signup -d '{"email":"a@b.com","password":"s3cret-password"}' -H 'content-type: application/json'`.

## Verification

The Makefile is the single source of truth (CI and pre-commit only call it).

```bash
make check   # lint (ruff + mypy + codespell) + tests — fast, offline
make ci      # what GitHub Actions runs verbatim: lint + coverage
make format  # auto-fix formatting + import order
```

## Layout

```
src/accounts/
  main.py        FastAPI app (health, error envelope, routers)
  config.py      settings from env / .env (RS256 keys, service token)
  auth.py        external-face identity resolver (RS256 bearer verify)
  security.py    RS256 token issuance/verification + password hashing
  schemas.py     Pydantic request/response models + PII-aware dump()
  db/            engine/session/Base + models + repositories (shared Postgres)
  routers/       auth.py, family.py (external), internal.py (service token)
scripts/         gen_keys.py (dev RS256 keypair)
tests/           unit_tests (SQLite) + integration_tests (real Postgres)
```
