# Build notes — round 3

- `backend/src/mtg_helper/services/new_cards/repository.py`: keys a Commander-Konstellation from
  every stored Commander Oracle ID even when facts are missing, and hides picks while unavailable.
- `backend/src/mtg_helper/services/new_cards/service.py`: records an expired in-flight provider
  call as an interrupted attempt, and derives admin finished counts from current Commander and
  candidate input hashes.
- `backend/tests/test_new_cards_automation.py`: covers missing-partner cache isolation, expired
  provider-result retry suppression, and stale finished-count invalidation.
- `frontend/components/admin-new-cards-panel.tsx`: disables an already-open start confirmation
  when polling reports that the process lock is active.
- `frontend/components/admin-new-cards-panel.test.tsx`: renders the locked confirmation safeguard.
- `docs/scryfall-publication-production.md`: closes autonomous New Cards admission and verifies
  durable claims/runs as part of the production drain procedure.

## Verification

```text
backend (disposable loopback PostgreSQL 16, port 55441):
  TEST_DATABASE_URL=postgresql://mtg@127.0.0.1:55441/mtg_helper_test
  uv run pytest -q -W error tests/test_new_cards_automation.py tests/test_new_cards_completion.py tests/test_new_cards_discovery.py
  75 passed in 38.55s

backend static checks:
  uv run ruff format --check .; uv run ruff check .; uv run ty check src/
  232 files already formatted; all checks passed

frontend fallback commands (pnpm unavailable):
  vitest 117 passed; tsc, oxlint, oxfmt passed; next build succeeded

full backend suite:
  1311 passed, 9 failed in 572.18s
```

There is no repository-wide `make gate`; the targeted acceptance checks and all static/frontend
checks are green. The nine full-backend failures are the evaluator-established BASE failures in
buylist, keyword extraction, planned changes, and tag classification; they are outside this round's
only requested FAIL/VIOLATES scope and were not changed.

## Deviations

No product-scope deviation. The existing untracked `GLOSSARY.md` was preserved. No paid model,
live data, OAuth prompt, deployment, or push was used.
