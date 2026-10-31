# Fresh bounded-setup Yuna/Meren comparison

## Authorization and frozen protocol

The user requested checking the fixed setup against both decks and, when asked to approve the
four-call baseline/refinement comparison, answered “dont care about token cost just run it”. This
is a fresh authorization, not a retry/resume of either older experiment. Limit this run to four
requests, no retries, no paid per-card reviews. The conservative reservation remains $0.1192; the
harness voluntarily retains its $0.15 guard rather than using the user's statement as open-ended
permission. No saved-deck changes, product/ranking changes or deployment are part of this check.

- Current `app-strategy-terms-v3` prompt, exact per-request catalog-enumerated schema and decoder.
- Yuna baseline → Meren baseline → Meren refinement → Yuna refinement. One complete replacement
  refinement per deck; never silently combine it with the baseline.
- Same source/ranking publication, commander facts, historical short strategy brief, 160-tag /
  120-keyword source menu, eight selected tags/eight keywords and production popularity order.
- Refinement receives its own decoded baseline searches, actual per-search/combined counts, the
  combined top ten facts, and deterministic first/second/middle/penultimate/last search samples.
  No reference identities, previous experiments' answers, grades or reference-overlap feedback.
- Freeze protocol, code/data/fixture hashes and baseline requests before calls. Freeze each exact
  refinement request before its attempt; exclusively create a new ledger. Refuse repeat/resume.
  Stop on invalid/incomplete output, unknown usage, provider errors or changed source/ranking.
- Source transactions are read-only on explicit isolated Compose. Preserve prior artifacts.

## Predeclared lead review rubric

After generation, review the alphabetical union of each arm's top twenty using complete Oracle
facts, commander and strategy only. Hide arm, rank and reference membership. This is one lead
assistant's source-grounded judgment on familiar regression decks, not an independent human blind
test. Each card receives one consistent rating per deck, a literal Oracle quote and a rationale.

| Rating | Contribution | Points | Interpretation |
| --- | --- | ---: | --- |
| direct | engine | 3 | Distinctive commander/declared engine connection supported by actual effects |
| direct | requested | 2 | Explicitly requested function without a distinctive engine interaction |
| support | generic | 1 | Useful ordinary infrastructure not otherwise explicitly requested |
| conditional | dependency | 0 | A meaningful unestablished package/resource is needed |
| uncertain | uncertain | 0 | Supplied facts/context do not justify a reliable fit claim |
| off_plan | liability | -1 | Unrelated or dominated by an unestablished liability |

Yuna's creature-based acceleration is explicitly requested, but a fixed-output mana creature is
not automatically a distinctive counter engine. Nor is every creature an engine fit merely
because Yuna can put counters on it or Meren can return it. Counter-scaling mana, actual counter
preservation/redistribution, repeatable beneficial entry/death effects, sacrifice outlets/rewards
and self-recursion can establish concrete engine connections. Generic cast/entry/death tags do not
certify those effects or compatibility. Distinguish permanent/player counters, cast versus entry,
front-face access, restrictions, and harmful triggers. No invented budget/bracket/pace/combo ban.

Primary adoption gate: weighted top-twenty fit improves on BOTH decks, off-plan counts do not
increase, and each refined pool retains >=90% of baseline-reachable reference identities. Report
distinctive-engine/requested/generic counts as well as scores. Also report first-page redundancy
qualitatively without imposing hard role quotas or tuning ranking. Reference hits at 10/20/50 and
full-pool coverage are separate recovery metrics, not precision/accuracy. Inspect them only after
writing and validating the Oracle-text grades. One sample per arm/deck cannot establish generality.

## Execution

Runner: `backend/scripts/bounded_result_aware_calls.py`; default prepares without spending.
Use `--live` once for the four requests; `--grade` applies validated local ratings and then computes
recovery. `--summarize` is an optional no-call recovery replay. All use explicit local Compose;
prepare/tests/replay/grade use `OPENAI_API_KEY=test`, the authorized run uses the existing secret
without printing it. The old experiment ledgers and live entry points are never reused.
