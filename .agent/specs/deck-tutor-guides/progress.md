# Ship progress

- Slug: deck-tutor-guides; approved spec, no clarification markers.
- Repository: C:\Users\mario\sources\mtg_helper
- Branch: ship/deck-tutor-guides (existing non-default branch reused).
- Original BASE: 7778d49a1f8fda1892053d1a7282df3dc2705d0d
- Slice-start HEAD: 7778d49a1f8fda1892053d1a7282df3dc2705d0d
- Existing working-tree modification: GLOSSARY.md; preserve it.
- Docker daemon: 29.5.3; explicit local Compose configuration valid.
- Required inputs read: approved slice spec; `GLOSSARY.md`; `VERIFY.md`; parent delivery/recovery
  contract, teaching rubric, and Yuna/Blue Farm fixtures in `.agent/specs/deck-tutor/spec.md`.
- Docker daemon: 29.5.3; explicit local Compose configuration valid.
- Completed implementation/test phase: red `test_setup_saves_mode_without_starting_a_guide` (404)
  followed by green Docker-only focused check (1 passed, 1 deselected). Added the Tutor HTTP seam,
  owner-scoped setup persistence, durable run storage, frozen card-fact capture, and bounded teacher
  adapters. `GLOSSARY.md` remains untouched.
- Evidence: this slice uses the authenticated Tutor HTTP, teaching, and rendered Tutor-view seams.
  Existing deck composition/identity, combo/source, model, schema, and test helpers remain to inspect
  before the first red test.
- Completed implementation/test phase: deterministic-teacher freshness HTTP test passed in Docker
  (`1 passed, 2 deselected`); actual card addition makes the persisted guide historical. Added the
  Tutor tab, API client/types, responsive accessible mode controls, explicit generation action, and
  readable historical/partial evidence UI. The focused Docker frontend test passed (`2 passed`).
- Completed verification: affected Tutor/deck HTTP suite (21 passed), focused Tutor suite (3 passed),
  backend ruff/format/type, frontend test (125 passed), typecheck, lint, format and production build all
  passed in Docker. Full backend pytest was attempted but remains blocked by a pre-existing buylist failure
  after 96 passes; see `build-notes.md`.
- Pending work: live-model fixture quality and local-browser acceptance, plus the unrelated full-suite
  buylist/backlog failures. No Tutor reference/chat/practice scope was added.
- Round 2 feedback read: `eval-1.md` is the sole feedback. It found startup schema ordering,
  canonical printing aggregation, exact evidence/provenance, and mode publication freshness failures.
  Tutor HTTP is the pre-agreed test seam for this repair round; begin with a failing Docker test for
  printing-only composition identity, then implement only the reported follow-ups.
- Next action: add and run the focused red Tutor HTTP/lifespan checks in Docker, then make the
  smallest schema, capture, and publication fixes before re-running affected Compose checks.
- Completed round 2 implementation/test phase: wrote the red Tutor HTTP printing-split freshness
  test (failed with `current: false`), then made it green. Added a blocked-generation Tutor HTTP
  test proving a saved mode change publishes the old run as `superseded`; focused suite is 5 passed.
  Normal existing-volume Compose startup now applies schema before run recovery and `/health` returned
  `{"status":"ok"`.
- Evidence: affected Tutor/deck/identity/snapshot/retrieval Docker suite is 41 passed; backend
  ruff/format/type and all five frontend Docker commands are green. The source evidence now stores
  exact local card facts, a pinned rules identifier/excerpt, active combo dependencies/outlets or a
  distinct timeout/unavailable/zero-results state. Reads and publication freshness skip source I/O.
- Pending handoff checks: evaluator should rerun browser/live-model fixture quality and its full
  source/persistence probes. No live model generation was made and `GLOSSARY.md` remains untouched.
- Next action: write round-2 notes and commit the focused recovery fixes for independent evaluation.
- Round 3 feedback read: `eval-2.md` is the sole repair scope. Preserve the pre-existing
  `GLOSSARY.md` edit. The authenticated Tutor HTTP, teaching, and rendered Tutor-view seams cover
  the reported faults: malformed/partial evidence, command-zone-aware teaching input, durable
  lifecycle/persistence matrices, and repeated running-state polling.
- Current phase: write focused red checks for the reported seams, then implement only the smallest
  fixes. Pending final Docker-only affected suites and the Verify gate.
- Completed round 3 implementation/test phase: the red command-zone opening-hand HTTP test now
  passes. Teacher output carries three typed, rendered, quantity-validated mainboard examples;
  command-zone facts are separate. Combo malformed coverage is distinct from zero results, partial
  rules/combo sources create visible warnings, and relevant pinned rule excerpts are retained.
  Commander and cEDH adapters now supply distinct teaching focus. Tutor polling continues across
  repeated running responses and stops on completion/unmount.
- Evidence: added real HTTP/SQL `evidence`, `runs`, and `persistence` selector coverage plus the
  requested shared fixture module. Docker affected backend gate is green: 45 passed, Ruff clean,
  257 files formatted, and ty clean. Docker frontend gate completed earlier this round: 31 files /
  127 tests passed, typecheck/lint/format/build green. Two broad backend-suite attempts exceeded
  tooling timeouts; their orphaned one-off containers were stopped before the final isolated gate.
- Next action: round 3 build notes and local commit only. No live generation or browser quality
  rerun was made, and the pre-existing `GLOSSARY.md` edit remains untouched.

## Final coordinator handoff
Three rounds used; coordinator gate-3 PASS (45 backend / 127 frontend tests and all static/build checks). eval-3 remains FAIL with S1 VIOLATES; review not reached. Spec marked blocked, report.md written. Evaluator cleanup complete; existing GLOSSARY.md preserved. Next action: resolve report open issues in a newly approved run.

## User-authorized continuation

- User requested continuation until finished; spec reapproved without changing acceptance or scope.
- Original BASE and slice-start HEAD remain `7778d49a1f8fda1892053d1a7282df3dc2705d0d`.
- Continuation starts from `29eb51fb83f22de149bf173312d2039c316398fb` on
  `ship/deck-tutor-guides`; Docker daemon 29.5.3 is available.
- Preserve the pre-existing `GLOSSARY.md` edit and earlier progress records.
- Next action: repair report/eval-3 failures test-first, complete deterministic verification matrices,
  then independently evaluate live teaching/browser acceptance and run both review axes.

## Continuation implementation

- Read `report.md` and `eval-3.md` completely, the parent recovery contract, teaching rubric, and
  exact Yuna/Blue Farm lists. Repair scope is limited to their open findings: last-good display
  freshness, nested malformed evidence, grounded teaching, reusable pinned fixtures, exact catalog
  aliases, and the named deterministic lifecycle/evidence/persistence matrices.
- Current phase: begin the pre-agreed HTTP/teaching/render seams with red regression checks. The
  pre-existing `GLOSSARY.md` edit remains preserved and untouched.

## Continuation completion

- Completed deterministic repair at the Tutor HTTP, teaching, and rendered-view seams. The displayed
  last-good run now controls historical state and warnings after a failed update. Nested malformed
  Commander Spellbook entries are rejected before capture; frozen evidence carries exact faces plus
  typed line zone/resource/outlet availability; prompts delimit all saved/source text as untrusted
  data and prohibit command-zone battlefield-ability claims.
- Reusable `tutor_fixtures.py` now exposes the complete supplied lists, exact Blue Farm flavor-name
  aliases, pinned face facts, hostile text, and deterministic Oracle/Pact/Breach evidence reused by
  HTTP/import tests. Alias ingestion preserves `flavor_name` from the normal Scryfall history and
  resolves an unambiguous exact alias before fuzzy matching.
- Tutor-run source references now protect pinned source snapshots from pruning and cascade with deck
  deletion. Deterministic coverage includes failed last-good display, malformed/timeout/zero-source
  distinctions, Oracle/Pact/Breach removal membership, faces, hostile source text, source pruning,
  lifecycle deduplication/failure, and cross-owner denial.
- Docker gates: backend affected suite/static checks `92 passed in 73.66s`, Ruff clean, `257 files
  already formatted`, Ty clean; frontend `31` files / `129` tests passed, typecheck/lint/format and
  production build passed.
- Live quality remains external: evaluator must first refresh the isolated catalog through the normal
  Scryfall sync so `card_aliases` is populated from real `default_cards` flavor names, then import the
  exact fixture (never seed production facts manually). The supplied aliases resolve to canonical
  City of Brass, Rograkh, Silence, Rhystic Study, and Lotus Petal; this conflicts with the parent
  prose that calls three canonical identities absent, so live assessment must preserve the printed
  fixture names and record that acceptance-text inconsistency rather than fabricate a different list.
