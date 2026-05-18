# Next Features
  - Chat page is dead — app/decks/[id]/chat/page.tsx is a 6-line redirect to deck detail. AI chat
  (/api/v1/decks/{id}/chat) exists on the backend. UI surface never built. (Can be remove no ai chat needed) Rmoev the chat page and all features also the backend for it all dependencies etc. is dont like the feature and want dead code from it gone
  - "Cuts" suggestion — not implemented. Would need backend endpoint + UI. (Nice to have feature implement this), important to not suggest a cut of combo pieces
  - Bracket validator — flag Game Changers, MLD, mass LD, fast mana, infinite combos vs declared bracket. You have brackets + combos data but no enforcement.

# Ideas
  - Goldfish playtest + health scorecard combo. Both rank highest on "thing enthusiasts actually use during deck tuning", reuse data you already have, no new backend integrations.
  - No mana-base auto-fix — suggest fixing color requirements / missing fetches.
  - No "owned in collection" badge on the deck card list (it's on suggestions, not on existing deck cards).
  - Budget swap suggestions — "deck €120 → here 8 swaps saving €60 with <10% function loss". You have prices + retrieval; missing the swap-finder.
  - Collection-aware build — "build from owned cards only" toggle in wizard. Collections exist but build doesn't filter.
  - Playtest / goldfish opening hand — shuffle, draw 7, mulligan to London, sim turns 1–4. Huge for tuning land count + curve. Nothing in app does this.
  - Mana base auditor — pip count per color, recommended land count by avg CMC, "you need 2 more white sources for double-pip turn 3". Curve chart shows shape but not color reqs.
  - Drag-and-drop categories — original big-move list, never built. (implement this)
  - Deck health scorecard — single panel: ramp 8/10 ⚠️, draw 6/10 ⚠️, removal 4/8 🟢, wipes 1/2, lands 36/37. You have category counts but not a verdict.
  - Buy list — deck minus collection → Cardmarket/TCG cart links.
  - No deck comparison — diff two builds, see overlap.
  - No version history / snapshots. No way to compare "before/after" a build session.
