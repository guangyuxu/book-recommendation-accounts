# Project Rules for Claude Code

This is the **accounts service (IdP + CRUD)** for the book-recommendation platform. It owns
signup/login and **issues RS256 access tokens** (holding the private key), and it is the **single
writer** of the family/member/child/reading-profile/policy tables. It exposes two faces: an
**external face** (user token) for the frontend's family management, and an **internal face**
(`/internal/*`, service token) that the agent calls instead of writing those tables directly. It
shares the agent's Postgres and its DB tooling, and OWNS that schema. The ORM models
(`src/accounts/db/models`) are the single source of truth for the schema; `init_db()`
(`CREATE SCHEMA IF NOT EXISTS` + `create_all`) builds it. The rules below mirror the sibling repos
so all projects hold one standard.

## PII & Security

This project stores and processes children's personal data (name, birthday, gender, reading
level). Treat all child/family data as high-sensitivity PII.

### Logging rules

- **Never log PII values in `logger.*` calls.** This includes: child names, birth dates,
  genders, reading interests, goals, user messages, family member names, and any field from
  `ChildProfile`, `FamilyMember`, `ChildReadingProfile`, `FamilyReadingPolicy`.
- When logging exceptions that may have touched DB rows or user input, log only the exception
  **type** (`type(exc).__name__`), never the full exception object or message.
  ```python
  # WRONG
  logger.warning("failed: %s", exc)
  # RIGHT
  logger.warning("failed: %s", type(exc).__name__)
  ```
- Safe to log: IDs (UUIDs), capability names, intent names, operation names, row counts,
  boolean flags.

### Authentication & identity rules

- **This service is the token ISSUER.** It holds the RS256 **private key** and signs access
  tokens; verifiers (the BFF, and this service's own external face) use the **public key** only.
  The private key never leaves this service.
- **Identity is derived server-side, never trusted from the client.** On the external face, verify
  the caller's token and derive `family_id` / `family_member_id` from the verified claims. A client
  must never be able to set `family_id` / `family_member_id` / `child_id` directly.
- The **internal face** (`/internal/*`) authenticates with a **service credential**
  (`X-Service-Token`), not a user token. `family_id` / `child_id` arrive as parameters over a
  trusted chain. It must be bound to an internal port / network and **never exposed to the public
  internet**. "No user auth" means service-credentialed — never unauthenticated.

### Authorization rules

- Every repository read/write that takes a `child_id` or `member_id` **must also filter by
  `family_id`** (`get_in_family(...)`). A query scoped only to `child_id` is a cross-family data
  leak. This holds on BOTH faces — the internal face does NOT skip the ownership check just because
  the caller is a trusted service.
- Any endpoint that acts on a child/member must confirm that child/member belongs to the
  caller's `family_id` before doing anything.

## Testing rules

- New repository methods that read data must have a cross-family isolation test: seed data
  under family A, query with family B's id, assert empty result.
- Endpoints that resolve identity must have a test that a caller cannot reach another family's
  data by passing a foreign id — including the internal face (foreign `family_id` param).

## Build & verification

The Makefile `CHECKS` section is the single source of truth for verification. Nothing restates
those commands: GitHub Actions (`.github/workflows/ci.yml`) runs `make ci` verbatim, and the
pre-commit hooks (`.pre-commit-config.yaml`) run `make check` on commit and `make ci` on push. So
local and CI cannot drift.

After every code change, run the everyday gate and make sure it is green before treating the work
as done. Do NOT report a task as complete while any check fails.

```bash
make check   # lint (ruff check + ruff format --diff + mypy + codespell) + test — fast, offline
```

Before pushing, run the full CI mirror (lint + tests under coverage, with a `fail_under` floor):

```bash
make ci      # what GitHub Actions runs verbatim: lint + coverage (offline)
```

If `make check` reports formatting diffs, run `make format` to auto-fix them. Optional: install
the local hooks once with `uv run pre-commit install` (runs `make check` + gitleaks on commit,
`make ci` on push). Focused subsets while iterating: `make lint`, `make test`, `make spell_check`.

Security tooling (does not block the code gate): ruff's `S` (flake8-bandit) rules run inside
`lint`; `make audit` (pip-audit) runs on a schedule (`.github/workflows/audit.yml`); gitleaks
scans for secrets in pre-commit and in CI; Dependabot opens dependency-update PRs.

RS256 keys and the service token are secrets: `keys/` is gitignored, and `.env` (never committed)
holds `ACCOUNTS_SERVICE_TOKEN`. Never commit a private key or token.
