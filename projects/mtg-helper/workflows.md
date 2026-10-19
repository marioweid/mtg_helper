# Core workflows

## Create or import a deck

Sign in with Google, then choose a commander and optional partner, name, strategy, and
target bracket. Description/keyword agents can help articulate a goal; text/URL import
can bring an existing list into the workspace.

## Build and refine

The builder stages are **Theme → Ramp → Draw → Interaction → Lands → Complete**.
Users can navigate stages, adjust targets and filters, load more candidates, inspect
source/ownership information, and add cards with appropriate quantities for basics.
Stage suggestions are deterministic retrieval results, not a fresh model-generated list.

The separate Coach accepts a question and bounded visible chat history, inspects the
current deck through tools, and returns unverified advice. Background turns publish
progress over SSE. Account preference learning, saved Coach memory, and thumbs-based
personalized ranking are no longer part of this workflow.

## Plan changes, buy cards, and record history

Keep physical cards separate from planned additions and cuts. Review plans and generate
Cardmarket shopping lists; complete selected plans through an atomic revision when the
physical changes are made. Experimental-origin additions recheck legality, color identity,
and copy limits during completion. Deck snapshots and revisions support history/comparison.
Export Moxfield-compatible text for use elsewhere.

Collections record owned printings/quantities and support ownership displays and scoped
building. Owning a card does not mean it is already in the physical deck.

## Playtest

Goldfish opening hands and early turns; inspect mana curve/composition and simulation
statistics. AI analysis and the separately gated optimizer are distinct from ordinary
manual playtesting. Simulations and generated advice are not competitive win-rate guarantees.

## Experimental discovery

- **Community Picks:** cached Moxfield/Archidekt commander evidence (the API still uses
  `top-picks`). This is separate from source-backed Discover.
- **New Cards:** explicitly analyze up to eight eligible released cards against the physical
  deck, inspect source rules, dismiss/undo, or plan one addition. No automatic analysis from
  reading the tab, preview support, or direct physical edits. See the
  [contract](../../docs/new-cards-pilot-contract.md).
- **Discover:** default-off, commander-only source-backed search and unverified advice.
  Optionally draft three strategies, choose/edit a goal, then explicitly generate cards.
  Reading/polling/filtering does not start a paid model request. See the
  [contract](../../docs/recommendation-pilot-contract.md).

## Refresh shared source data

Admin sync publishes Scryfall cards, printing history, and canonical tags atomically;
failed publication retains the last good generation. Production's daily worker refreshes
Scryfall and runs the full legacy enrichment/tagging pipeline every seventh day.
Local development uses manual Admin sync, with empty-catalog initialization when startup
maintenance is enabled. See [OPERATIONS.md](../../OPERATIONS.md#card-data-sync).
Canonical tag publication does not yet replace all legacy label consumers.
