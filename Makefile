# ─────────────────────────────────────────────────────────────────────────────────────
# VERIFICATION MAP — this Makefile is the single source of truth. ci.yml and
# .pre-commit-config.yaml only CALL these targets (never restate commands), so no drift.
#
#   ci    = lint + coverage            ← GitHub Actions (verbatim) + pre-push hook
#   check = lint + test                ← everyday local + pre-commit hook
#   lint  = lint_ruff + lint_format + typecheck + spell_check
#
#           lint_ruff .... ruff check          spell_check .. codespell
#           lint_format .. ruff format --diff   test ......... pytest
#           typecheck .... mypy                 coverage ..... pytest + coverage report
#
#   coverage RUNS the full test suite (so `ci` does not skip tests); `check` is fully offline.
#   audit (pip-audit) is NOT in ci/check — it needs the network, so it runs on a schedule
#     (.github/workflows/audit.yml); run it by hand with `make audit`.
#   fixers (manual):  format = fix formatting + imports    spell_fix = fix spelling
#   (k8s / deploy targets are intentionally omitted here — infra is handled separately.)
# ─────────────────────────────────────────────────────────────────────────────────────

.PHONY: all \
	lint_ruff lint_format typecheck spell_check audit test coverage \
	lint check ci format spell_fix \
	keygen init-db run help

# Default target executed when no arguments are given to make.
all: help

######################
# CHECKS
######################
# Single source of truth for verification. Nothing else restates these commands:
#   - GitHub Actions (.github/workflows/ci.yml) runs `make ci` verbatim.
#   - pre-commit (.pre-commit-config.yaml) runs `make check` on commit and `make ci` on push.
# So local == CI by construction. Audit is excluded (needs the network -- see below).
#
# Everyday use:  `make check`  (fast, offline: lint + test; lint = ruff + format + mypy + codespell)
# Before push:   `make ci`     (what GitHub Actions runs verbatim: lint + coverage; fully offline)
# The default suite (`test`/`coverage`) is the fast SQLite unit tests under tests/unit_tests.
# `make integration` runs tests/integration_tests against a throwaway REAL Postgres started by
# pytest-postgresql (local initdb/pg_ctl -- offline, but needs the Postgres binaries on PATH), so it
# is kept OUT of the blocking gate and run on its own (opt-in / separate CI job).

CHECK_PATHS = src/ tests/

# -- atomic checks: each is the ONE definition of that check --
lint_ruff:               ## ruff lint rules (import sorting included via [tool.ruff] lint.select)
	uv run ruff check $(CHECK_PATHS)

lint_format:             ## fail if any file is unformatted (does NOT modify files; run `make format` to fix)
	uv run ruff format --diff $(CHECK_PATHS)

typecheck:               ## mypy -- config-driven ([tool.mypy]: strict, files = src/accounts)
	uv run mypy

spell_check:             ## codespell over the repo
	uv run codespell --skip ./.git --ignore-words .codespellignore .

audit:                   ## dependency vulnerability scan (hits the network)
	uv run pip-audit

test:                    ## fast unit suite (SQLite; the offline gate)
	uv run pytest tests/unit_tests

coverage:                ## runs the unit suite under coverage + report (this is how `make ci` runs tests)
	uv run coverage run -m pytest tests/unit_tests
	uv run coverage report

integration:             ## end-to-end business flows vs a throwaway REAL Postgres (needs pg binaries on PATH)
	uv run pytest tests/integration_tests

# -- composites --
lint: lint_ruff lint_format typecheck spell_check  ## all static checks: ruff + format + mypy + codespell (fast, offline)
check: lint test                                   ## everyday gate after code changes: lint + tests (offline)
ci: lint coverage                                  ## code gate CI runs verbatim: lint + tests(coverage); coverage RUNS the suite
# `audit` is intentionally NOT in `ci`: it needs the network, so it runs on a schedule
# (.github/workflows/audit.yml), not on the per-push/PR blocking path. Run it locally with `make audit`.

######################
# AUTO-FIXERS  (the read-only checks live in the CHECKS section above)
######################

format:                  ## auto-fix formatting + import order (the fixer for lint_format)
	uv run ruff format $(CHECK_PATHS)
	uv run ruff check --select I --fix $(CHECK_PATHS)

spell_fix:               ## auto-fix spelling across the repo
	uv run codespell --skip ./.git --ignore-words .codespellignore -w .

######################
# KEYS / DATABASE / RUN
######################

keygen:               ## Generate an RS256 keypair into keys/ (dev; keys/ is gitignored)
	uv run python scripts/gen_keys.py

init-db:              ## Create the schema + tables from the models (CREATE SCHEMA IF NOT EXISTS + create_all)
	uv run python -c "from accounts.db import init_db; init_db()"

run:                  ## Run the API locally (http://localhost:8000/docs)
	uv run uvicorn accounts.main:app --reload --host 0.0.0.0 --port 8000

######################
# HELP
######################

help:
	@echo '--- checks (local == CI; see .github/workflows/ci.yml) ---'
	@echo 'check                        - everyday gate after code changes: lint + test (offline)'
	@echo 'ci                           - faithful GitHub CI mirror: lint + coverage (offline)'
	@echo 'lint                         - static checks: ruff check + ruff format --diff + mypy + codespell'
	@echo 'format                       - auto-fix formatting + import order'
	@echo 'test                         - run the fast unit suite (tests/unit_tests, SQLite)'
	@echo 'integration                  - run end-to-end flows vs a throwaway real Postgres (needs pg binaries)'
	@echo 'coverage                     - run tests with a coverage report'
	@echo 'spell_check                  - check spelling across the repo'
	@echo 'spell_fix                    - auto-fix spelling across the repo'
	@echo 'audit                        - dependency vulnerability scan (pip-audit; needs network)'
	@echo 'keygen                       - generate an RS256 keypair into keys/ (dev)'
	@echo 'init-db                      - create the schema + tables from the models (create_all)'
	@echo 'run                          - run the API locally with reload (port 8000)'
