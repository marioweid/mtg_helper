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
- Next action: hand off the committed round for evaluation; evaluator should independently run slice checks.
