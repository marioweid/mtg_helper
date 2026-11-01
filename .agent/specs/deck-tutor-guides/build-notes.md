# Build notes — round 3

- `backend/src/mtg_helper/models/tutor.py`: added typed worked-opening-hand output.
- `backend/src/mtg_helper/services/combo_service.py`: reject malformed Commander Spellbook result coverage.
- `backend/src/mtg_helper/services/tutor/{teaching,service,commander,cedh,evidence}.py`: separate command zone,
  validate rendered mainboard hands, specialize mode focus, retain relevant rules, and expose source gaps.
- `backend/tests/test_tutor_guides.py`: added real HTTP/SQL evidence, run, and deletion persistence checks.
- `backend/tests/tutor_fixtures.py`: exposes the exact parent fixture lists without stock-list substitution.
- `frontend/components/tutor-panel.tsx`: polls through repeated running responses and renders verified worked hands.
- `frontend/components/tutor-panel*.test.tsx`, `frontend/lib/types.ts`: covered polling lifecycle and typed guide output.

Gate: Docker affected backend command from `VERIFY.md` plus Tutor/deck/identity/snapshot/source suites.
Final summary: `45 passed in 38.37s`; `All checks passed!`; `257 files already formatted`; `All checks passed!`.
The Docker frontend gate completed earlier this round: 31 files / 127 tests passed; typecheck, lint, format, and
production build passed.

Two full-backend-suite attempts exceeded command time limits and their overlapping one-off containers caused a
transient test-schema deadlock. Both containers were stopped; the final isolated affected gate above is green.
No spec deviation or harness change was made. The existing user edit to `GLOSSARY.md` was preserved unchanged.
