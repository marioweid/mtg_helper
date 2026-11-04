# Ship progress

## Final parser-envelope repair

- Eval-11 isolated a Starlette-base HTTP 400 parser exception missed by the FastAPI-subclass catch.
- Next: prove invalid UTF-8 regression red, catch the documented framework base class locally,
  and rerun affected Docker checks plus the evaluator's real-TCP probe. Teacher/model/evidence and
  frontend remain unchanged from the six passing live guides in eval-10; no new paid runs needed.
- Red: both invalid-UTF-8 HTTP regressions failed with the observed default `detail` envelope.
- Green: Tutor catches Starlette's base exception, preserves headers/status and returns a sanitized
  UTF-8 JSON recovery message. Final coordinator Docker gate: 163 affected backend tests passed;
  Ruff, formatting and Ty passed. Next: independent real-TCP confirmation and final review.

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
- On 2026-11-02 the user explicitly chose to keep the exact Blue Farm deck and correct the
  contradictory rubric. Parent AC5 and slice AC2 now recognize Rhystic Study / Silence / Lotus Petal
  under their supplied flavor names; absent-card exclusions remain for genuinely absent identities.
  Primary Scryfall evidence and the original contradiction remain documented in `eval-4.md`.
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

## Eval-4 repair

- Feedback read in full from `eval-4.md`; repair scope is limited to its AC2â€“AC7 failures and S1â€“S4.
- Current phase: add red HTTP/render regressions for durable intent, read-only state, publication
  interleaving, known-fact warnings, transferred ownership, malformed sources, and initial load errors.
- Original BASE and slice-start HEAD remain `7778d49a1f8fda1892053d1a7282df3dc2705d0d`; repair starts
  at `2c4c55d1f06ebc3f3e313cf487744f377de9c83a`. Preserve the pre-existing `GLOSSARY.md` edit.
- Completed deterministic repair: source intent is durable before fallible evidence capture; malformed
  root/nested Spellbook data and corrupt rules are retained as distinct source gaps; reads are
  observational; physical composition writers and publication serialize on the deck row and a run
  publication locks its run before checking current inputs.
- Completed deterministic coverage: the named selectors now exercise relevant/irrelevant freshness,
  the complete malformed source matrix, duplicate request keys/tabs, interruption recovery, real
  quantity publication race, transferred-owner setup/generation, late deletion publication, and
  saved known banned/off-color warnings. No model call was made during these checks.
- Final Docker gate: affected backend source/identity suite `113 passed in 81.48s`; Ruff clean,
  `257 files already formatted`, Ty clean; frontend `31` files / `130` tests passed, typecheck,
  lint (0 warnings/errors), format and production build passed.
- Parent AC5 and slice AC2's approved correction is preserved without editing acceptance here: the
  exact Blue Farm deck recognizes the supplied Rhystic Study, Silence, and Lotus Petal flavor aliases.
- Next action: commit the scoped round-5 repair, leaving the pre-existing `GLOSSARY.md` modification
  unstaged for its owner. Live re-evaluation remains pending and must issue fresh explicit runs.

## Eval-5 repair

- Feedback read in full from `eval-5.md` plus its independent teaching, API/SQL, and scope audits.
  Repair scope is limited to their remaining AC2/AC4/AC5/AC7 and static-deliverable findings:
  diverse actual-list hand candidates with reliable typed decisions, malformed HTTP/numeric combo
  coverage, a deck-wide active-run guard across ownership transfer, bounded teaching input, portable
  complete fixture lists/pinned facts, and an honest baseline schema-gate record.
- Current phase: add red checks only at the approved Tutor HTTP/teaching seams, implement the smallest
  bounded deep-module changes, then run Docker-only affected suites and the full VERIFY gate. Preserve
  the pre-existing `GLOSSARY.md` edit and all previous evaluation evidence.
- Completed round 6 repair: named structured model fields now require keep, mulligan, and
  context-dependent hand outputs before conversion to the existing rendered list; malformed output still
  fails once, without a hidden retry. Candidate construction uses frozen mainboard quantities plus land,
  CMC, and mana-cost facts to offer a balanced action hand, a low-mana curve-stress hand, and mixed
  alternatives rather than all-land examples. No fixture card or primer is selected in production code.
- Completed source/lifecycle repair: HTTP-200 invalid JSON and non-finite popularity become malformed
  Commander Spellbook coverage; oversized descriptions/evidence are rejected before the model with no
  silent Oracle/rule truncation; the active-run index and repository guard are deck-wide across transfer.
  Full Yuna/Blue Farm lists and real pinned facts are now portable test data, and the schema-upgrade test
  drops its dependent test-local view before simulating the older tag tables.
- Final Docker-only verification: affected Tutor/CRUD/import/identity/snapshot/source/schema suite
  `122 passed in 95.10s`; no-DB suite `565 passed, 656 deselected in 9.91s`; Ruff clean; `257 files
  already formatted`; Ty clean. Frontend gate: `31` files / `130` tests passed, typecheck passed, lint
  `0 warnings and 0 errors`, format clean, and production build compiled successfully.
- No paid model call, live-data operation, source refresh, or acceptance edit was made. Fresh six-attempt
  live teaching evaluation is intentionally pending on the repaired committed HEAD; the pre-existing
  `GLOSSARY.md` edit remains unstaged.

## Round 7 - static-review repair

- Read `review-spec.md` and `review-standards.md`; repair scope is limited to reusable real Yuna pinned facts with
  deterministic Tutor HTTP/evidence consumption, plus the four documented overlong Tutor-panel lines.
- Docker Compose local catalog supplied the exact Yuna commander and counter/combat-engine facts; no external or paid
  source was used. Red HTTP/evidence collection failed before `YUNA_PINNED_FACTS` existed, then its focused check
  passed after the portable fact fixture and consumer were added.
- Final verification is green: Tutor HTTP fixture check (`52 passed`), no-DB suite (`565 passed, 657 deselected`),
  backend Ruff/format/Ty, and all five frontend checks (`130` tests, typecheck, lint, format, build). No paid or live
  operation was made; the pre-existing `GLOSSARY.md` edit remains unstaged.

## Round 8 — eval-7 repair

- Feedback read in full from `eval-7.md` and `artifacts/eval7-teaching.md`. Repair scope is limited to the failed
  live teaching quality and the two deterministic scope violations: Tutor-only stronger model/reasoning budget,
  complete portable pinned facts for both supplied fixtures, and bounded candidate work for extreme quantities.
- User explicitly approved the Tutor-only `gpt-6.1-sol` high-reasoning intervention. The shared default model remains
  `gpt-5.6-luna` for Coach, Discover, and every other existing consumer. Preserve the pre-existing `GLOSSARY.md` edit.
- Original BASE and slice-start HEAD remain `7778d49a1f8fda1892053d1a7282df3dc2705d0d`; this repair starts at
  `90b5edfb8dfaff318dab99610701cab8efb8796c`. Docker 29.5.3 and explicit local Compose configuration are available.
- Current phase: export real canonical card facts from the already synchronized isolated Compose catalog, add red
  Tutor HTTP/model/candidate-bound regressions at the approved seams, then implement the smallest scoped repair.
- Completed implementation: Tutor alone constructs `gpt-6.1-sol` through the existing shared constructor, requests
  high reasoning with a 16,000-token Responses/usage bound, keeps `retries=0`, and retains its one-request/no-tools
  contract. Coach and Discover remain on `gpt-5.6-luna`. The general evidence-grounded prompt now requires exact
  resource/timing/text checks and Tutor evidence includes CR 302.6.
- Completed fixture and input-bound repair: `backend/tests/fixtures/tutor_catalog.json` contains 185 real canonical
  local-catalog facts plus exact supplied-name mappings, faces, legalities, and generation provenance for both lists.
  Deterministic Tutor HTTP tests seed full Yuna 99+1 and Blue Farm 98+2 lists, retain printed aliases, assert every
  frozen fact/quantity, and cover Shelinda, Kraum, and Tymna. Candidate work now caps each identity at seven copies
  while frozen evidence preserves the true quantity. Partner color identity is used for physical additions and its
  regression still rejects an outside color.
- Final scoped Docker checks are green: Tutor/CRUD/OpenAI regression suite `88 passed in 83.43s`; expanded affected
  source/identity/schema suite `141 passed in 99.87s`; no-DB suite `567 passed, 662 deselected in 9.93s`; Ruff,
  format, and Ty are clean; all five frontend commands pass (`31` files / `130` tests, typecheck, zero lint warnings,
  format, build). No live or paid model call, source refresh, environment, or volume change was made.
- A one-time complete backend pytest run was attempted as required and is not a green gate: `1192 passed, 10 failed,
  27 errors`. The failures are unrelated pre-existing full-suite isolation/schema assumptions (buylist/price state,
  copy-local loopback host, stale `cards.tags` swap tests, and duplicate source fixture). They are outside eval-7's
   exclusive repair scope; affected Tutor and VERIFY-required checks above are green. Next action: commit this scoped
   round with the complete portable dataset and report the unrelated complete-suite baseline honestly.

## Round 9 — eval-8 repair

- Feedback read in full from `eval-8.md` and its real FastAPI/SQL/SDK transport artifact. Repair scope is limited to
  AC2's rejecting a complete detailed model output at the arbitrary 24,000-character schema bound, and AC5/S1's
  inherited OpenAI SDK retries. The approved Tutor-only stronger model, 16,000-output-token bound, no-tools and one
  manual action contracts remain unchanged; Coach, Discover, and the shared default must retain their current SDK
  defaults.
- Current phase: add red boundary/output, frontend wrapping, and real Tutor HTTP/SQL external-transport regressions
  at the approved Tutor seams. Then widen only the typed persisted-guide bound and construct/close a Tutor-only
  zero-retry SDK client through the existing model factory seam. Preserve the pre-existing `GLOSSARY.md` edit.
- Completed repair: typed model and persisted-guide content now allow up to 64,000 characters, aligning with the
  existing 16,000-token bound while still rejecting larger output. The prompt targets 12,000–24,000 focused characters,
  avoiding needlessly long guides without throwing away complete 25,000–40,000-character results. The existing Tutor
  guide view wraps permitted content, now protected by a 40,000-character render check.
- Completed transport repair: Tutor alone passes an explicitly owned `AsyncOpenAI(max_retries=0)` to the existing
  `OpenAIProvider` factory path and closes it after every request. Shared factory callers still get the SDK default
  retry budget of two. The real FastAPI/SQL/Pydantic-AI/SDK path is exercised through external-only MockTransport for
  HTTP 500, 429, and timeout: each attempt is exactly one request, terminal failures retain last-good content, and
  GET/same-key reads issue no new provider request.
- Final scoped Docker verification: expanded Tutor/CRUD/import/identity/snapshot/source/schema/model suite `146 passed
  in 136.79s`; Ruff, format, and Ty clean. Frontend gate: 31 files / 131 tests passed, typecheck, zero-warning lint,
  format, and production build passed. No paid model or live-data call occurred; the pre-existing `GLOSSARY.md` edit
  remains unstaged.

## Round 10 — standards and approved output-policy repair

- Feedback scope: `review-standards.md` hard findings only, plus the user's explicit approved Tutor output policy.
  The pre-existing user-owned `GLOSSARY.md` modification remains untouched and excluded from the commit.
- User policy: generated/persisted Tutor guide title, content, and worked-hand explanation have no application character,
  output-token, or cost caps. Provider-native limits apply. Input safety limits, exactly one request, no callable tools,
  zero SDK/agent retries, owned-client close, exact three seven-card validation, and Tutor-only `gpt-6.1-sol` high
  reasoning remain intact; Coach and Discover retain the Luna default.
- Red-to-green evidence: the model/persistence boundary test initially failed against the 200/1,200/64,000 Pydantic
  limits and the absent optional settings API. It now proves a guide above 64,000 characters and explanations above
  1,200 characters are retained intact; existing malformed-output/durable-failure coverage remains green. The real SDK
  transport fixture asserts outgoing Tutor requests omit `max_output_tokens`, while the request spy asserts no
  Pydantic-AI output-token usage cap.
- Tutor router failures now go through the application `TutorError` handler and its standard `error: {code, message}`
  envelope, including the email-required status; owner/status semantics are unchanged. SQL and cEDH detail literals
  now observe the 100-column standard without semantic changes.
- Final Docker-only checks: affected SQL/HTTP/model suite `148 passed in 114.64s`; no-DB suite `569 passed, 667
  deselected in 10.80s`; Ruff clean; `257 files already formatted`; Ty clean. Frontend gate: `31` files / `131` tests
  passed, typecheck passed, lint `0 warnings and 0 errors`, format clean, production build compiled successfully.
- No paid/model call, live-data operation, environment/volume change, acceptance edit, or unrelated full backend-suite
  retry was made. Next action: commit this scoped round excluding `GLOSSARY.md`, then hand off for independent evaluation.

## Round 11 — eval-10 request-validation repair

- Feedback read in full from `eval-10.md`; its sole failure is Scope S1: new Tutor framework
  request-validation responses use FastAPI's `detail` payload instead of the required error envelope.
- Original BASE and slice-start HEAD remain `7778d49a1f8fda1892053d1a7282df3dc2705d0d`; repair starts at
  `368c043880e56c7b9c0ca20979a63d39bc67654a`. Preserve the pre-existing user-owned `GLOSSARY.md` edit.
- Current phase: add a failing authenticated Tutor HTTP regression for invalid mode/request key, malformed deck ID,
  absent or malformed JSON, and no persisted intent; then add a route-local normalized validation envelope without
  altering legacy routes, teaching, model, fixture, schema, or UI code. Recheck auth and ownership status behavior.
- Red-to-green evidence: the new Tutor HTTP check first failed on FastAPI's absent `error` field, then passed after
  route-local handling. Invalid mode, malformed request key/path UUID, missing body, and malformed JSON now return
  422 `ErrorResponse` values with a nonempty code/message and no submitted value; they persist no Tutor run.
- Completed narrow verification: Docker Tutor/CRUD/auth suite `93 passed in 84.12s`; Docker Ruff format `257 files
  already formatted`, Ruff check and Ty `All checks passed!`. The full six live generations and already-passing unchanged
  frontend gate were deliberately not repeated; this repair cannot invoke the model.
- Production teacher/model proof: `git diff --exit-code 368c0438 -- backend/src/mtg_helper/services/tutor/teaching.py
  backend/src/mtg_helper/services/agents/_model.py` is clean. No teaching, model, fixture, prompt, schema, or Tutor UI
  code changed. Next action: commit the narrow repair excluding the pre-existing `GLOSSARY.md`, then final evaluation.
