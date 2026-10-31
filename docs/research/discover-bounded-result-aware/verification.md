# Offline verification before spending

All checks ran in explicit local Compose containers with `OPENAI_API_KEY=test`. No retries,
reference recovery or paid model grading were used for harness verification.

- **42 scoped tests passed:** `test_bounded_result_aware.py`, `test_result_aware_calls.py`,
  `test_result_aware_eval.py`, `test_term_selection.py`, using `-m no_db -W error`.
- New-run checks exercise fresh v3 requests, checkpoint-before-send, four-call scope, own-baseline
  observations only, decoded persisted queries, packet deduplication/hidden metadata, no-repeat,
  source changes, invalid output, missing usage, timeouts, oversized input and frozen rubric binding.
- The engine-versus-requested grading check was observed fail with engine weight deliberately
  changed from three to two; restored to three before freezing or spending, then passed.
- Scoped Ruff lint/format and ty checks pass for the new runner and tests.
- Preparation initially exposed the Compose layout's import path (`/app/src`) differing from the
  read-only checkout path (`/workspace/backend/src`). The source hash now uses the checkout path
  and explicitly verifies that the imported module's bytes match it. This was corrected offline,
  before `inputs.json` or a paid attempt existed; no interrupted paid call was retried.
- The prior implementation check passed 138 affected tests, full-source typing and scoped lint/
  format checks; current production matching SQL and the v3 contract are unchanged in this run.

Use the `BackendCheck` helper from `VERIFY.md`:

```powershell
BackendCheck pytest -q -W error -m no_db tests/test_bounded_result_aware.py tests/test_result_aware_calls.py tests/test_result_aware_eval.py tests/test_term_selection.py -o cache_dir=/tmp/pytest-cache
BackendCheck ruff check scripts/bounded_result_aware_calls.py tests/test_bounded_result_aware.py
BackendCheck ruff format --check scripts/bounded_result_aware_calls.py tests/test_bounded_result_aware.py
BackendCheck ty check scripts/bounded_result_aware_calls.py tests/test_bounded_result_aware.py
```

Preparation, local grading and recovery replay need a writable mount for only this artifact folder,
plus the read-only full checkout. Use the existing authorized key only for the one `--live` run;
never remove `attempts.json` or resume its live entry point after any attempted call.
