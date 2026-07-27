"""Test suite. Two suites, one layout law -- identical in the sibling repos (agent, service).

    unit_tests/         fast + offline; the tree MIRRORS `src/accounts/` (one dir per subpackage).
                        Run by the blocking gate: `make test` / `make coverage` / `make ci`.
    integration_tests/  end-to-end journeys vs a real ephemeral Postgres; organized by FLOW.
                        Opt-in: `make integration` (kept out of `make ci`).

Each suite's `__init__.py` states its own rules.
"""
