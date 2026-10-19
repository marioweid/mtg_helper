# Round 1 gate

- Backend VERIFY commands: PASS. Live-development/observability tests: 39 passed;
  Ruff check, Ruff format check (239 files), and `ty check src/`: passed.
- Frontend `corepack pnpm lint`, `typecheck`, `test`, `build`: PASS;
  zero lint warnings/errors, 106 tests passed, production build completed.
- Initial bare `pnpm` was unavailable; Corepack successfully ran the pinned package manager.
- Isolated database gate: FAIL/unavailable. `docker compose up -d --wait postgres`
  failed: Docker daemon pipe `//./pipe/docker_engine` does not exist.
- Overall gate: FAIL. Database and isolated browser acceptance remain required;
  offline checks do not substitute for them. No live mode or environment changes made.
