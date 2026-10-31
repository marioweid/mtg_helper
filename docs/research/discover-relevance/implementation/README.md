# Discover relevance implementation verification

The user approved implementing richer term selection and filtered/global-popularity ordering,
with data-preserving saved-search migration and the existing simple manual-override UI. No equal
role quotas, strong-only filter, model changes, new paid calls, or card-specific exclusions.

The local replay in `results.json` uses the previously frozen experimental selections, renamed
from the experiment's `lanes` container to the application's `queries` contract. It exercises the
production matcher and response models with front-face scopes and global-popularity ordering.
Reference lists remain scoring-only; no saved strategy or physical/pending card is edited.
This verifies integration and deterministic matching, not a fresh evaluation of the updated prompt
or general recommendation accuracy. Original paid requests, outputs and result files stay intact.

## Result

| Frozen selection through production matching | Yuna | Meren |
| --- | ---: | ---: |
| Reference hits in first 10 | 1 | 6 |
| Reference hits in first 50 | 11 | 20 |
| Reference identities anywhere in the pool | 46/65 | 29/66 |
| Eligible filtered pool | 2,729 | 1,326 |

The production front-face check removes six matches from each experimental filtered pool without
reducing reference coverage. There is no role balancing and no membership-strength filter. Off-list
cards are not automatically incorrect, and cast/entry/death semantic fit remains unverified by tags.

The new `app-strategy-terms-v2` profile includes full commander facts and source descriptions, uses
the richer bounded catalog, and explicitly discourages tiny filler searches and cast/reanimation
confusion. Its live model output was **not** regenerated for this implementation; all paid checks
remain the previous four-call experiment. Regression tests validate the new schema and workflow.

## Verification

- **112 backend checks** pass across Discover matching/setup, old pilot accounting/strategy/artwork,
  pure contracts, and preserved experiment checks. **23 frontend checks** pass for the state machine
  and view, including filter retention and explicit manual replacement.
- Backend Ruff lint/format and ty, frontend lint/format/type checks and production build pass in
  Docker. Function/parameter limits are checked on changed production modules and the replay.
- The ranking API check was observed red before implementation. A temporary in-container mutation
  changing front-face scope back to combined type lines made the Battle/creature regression fail;
  the mutation never touched checkout files, and the unmodified scoped suite is green.
- Upgrade was tested twice on disposable `_test` data before local app startup. The isolated app
  migration preserved its complete saved-strategy fingerprint
  `884ab6f97d3fb185a9478fc53460bfa1`, 536 physical-card rows, zero pending plans, 13 historical runs,
  and 19,600 microdollars of historical holds. No saved criteria were regenerated.
- Compose app health is OK. A browser using the existing local identity loaded the migrated Yuna
  strategy and twelve deck-excluded results, showed the global-popularity explanation and migrated
  search filters, and reported no Discover error. Only read/expand actions were used, not Find cards,
  planning, dismissal, or a save.
- Historical baseline SQL is now archived in `profiles_discover_v1.py`; the old experiment still
  reproduces its original `summary.json` and `controls.json` exactly through local replay. Its spent
  paid-call guard remains one-shot; code-version changes deliberately cannot authorize new calls.

Existing strategies immediately receive the new ordering but keep their chosen criteria. To obtain
the richer criteria, use **Change strategy → Find cards** explicitly. New Cards, Community Picks,
commander strategy drafting, manual card categories, and production/live deployment are unchanged.

Run from the repo root against the preserved isolated source publication:

```powershell
docker compose -f docker-compose.yml run --rm --no-deps --volume "${PWD}:/workspace:ro" --volume "${PWD}/docs/research/discover-relevance/implementation:/results" --workdir /workspace/backend -e UV_PROJECT_ENVIRONMENT=/app/.venv -e LOCAL_DEV_AUTH=false -e OPENAI_API_KEY=test backend uv run --frozen python -m scripts.verify_discover_ranking --output /results/results.json
```
