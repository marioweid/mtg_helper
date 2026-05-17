# Ideas

- Make It work locally again, refactor docker compose for local setup and remote only ingests the cloudflare

⏺ Repo recon done. App has: deck CRUD, staged AI build wizard, collections, AI suggest/chat (chat now redirects to deck page), combos, tags, EDHREC, Moxfield import/export, bracket, price, preferences,
  onboarding. Last commit: commander card preview modal + mechanic chips.

  Here gaps I'd want as Commander player + UI ideas. Picking high-impact, not yak-shave.

  Player-useful gaps

  1. Playtest / goldfish opening hand — shuffle, draw 7, mulligan to London, sim turns 1–4. Huge for tuning land count + curve. Nothing in app does this.
  2. Mana base auditor — pip count per color, recommended land count by avg CMC, "you need 2 more white sources for double-pip turn 3". Curve chart shows shape but not color reqs.
  3. Deck health scorecard — single panel: ramp 8/10 ⚠️, draw 6/10 ⚠️, removal 4/8 🟢, wipes 1/2, lands 36/37. You have category counts but not a verdict.
  4. Cuts / Maybeboard — track "considered but not in", with reason. Right now reject = gone. Enthusiasts iterate.
  5. Bracket validator — flag Game Changers, MLD, mass LD, fast mana, infinite combos vs declared bracket. You have brackets + combos data but no enforcement.
  6. Budget swap suggestions — "deck €120 → here 8 swaps saving €60 with <10% function loss". You have prices + retrieval; missing the swap-finder.
  7. Collection-aware build — "build from owned cards only" toggle in wizard. Collections exist but build doesn't filter.
  8. Buy list — deck minus collection → Cardmarket/TCG cart links.
  9. Paste-to-import — paste raw decklist text, auto-resolve. Currently only URL import + manual add.

  My recommendation if you want one to start:
  - Goldfish playtest + health scorecard combo. Both rank highest on "thing enthusiasts actually use during deck tuning", reuse data you already have, no new backend integrations.

Honest audit. Three buckets.

  Half-shipped / inconsistent

  - Chat page is dead — app/decks/[id]/chat/page.tsx is a 6-line redirect to deck detail. AI chat
  (/api/v1/decks/{id}/chat) exists on the backend. UI surface never built. (Can be remove no ai chat needed)
  - "Cuts" suggestion — not implemented. Would need backend endpoint + UI. (Nice to have feature implement this)
  - Drag-and-drop categories — original big-move list, never built. (implement this)
  - Per-card actions in grid view — only via modal click. No quick remove or quick categorize without opening
   modal.
  - No browser verification of hero / popover / grid / command bar / commander section / new deck list tile.
  All passes type-check, none confirmed visually. (Checks passed i tested it)
  - 8 pre-existing ty check warnings in backend — config.py / main.py / cards.py / ai_service.py /
  deck_service.py. Not mine but they've been ignored.
  - handleSetCategories / handleRemoveCard reload the entire deck after every action. Visible flash on the
  new visual grid. ( fix this, can be nicer and smoother)

  Product gaps

  - No within-deck search / filter / sort (CMC, color, price, name). Once decks exceed ~50 cards, list
  scanning gets rough.
  - No version history / snapshots. No way to compare "before/after" a build session.
  - No deck sharing — public URLs, share links, embed.
  - No playtest / sample hand — visualize a 7-card opener.
  - No deck comparison — diff two builds, see overlap.
  - No mana-base auto-fix — suggest fixing color requirements / missing fetches.
  - No combo highlight in deck view — combos exist as a tab but the cards in the regular list don't flag
  "this card completes a combo."
  - No "owned in collection" badge on the deck card list (it's on suggestions, not on existing deck cards).
  - No keyboard shortcuts anywhere.
  - No CSV deck import — text only. Most Moxfield exports include set/quantity.

  Quality / debt

  - No frontend tests at all.
  - Backend tests blocked by env — pytest needs local postgres. Recent backend change (color_identity column)
   not test-covered.
  - Visual identity stops at deck pages — /collections, /preferences, /admin, /onboarding, /signin still use
  the old flat style.
  - No empty-state polish on collections, preferences (deck page has one).


  Which thread?

## Optional nice to have

- Take the mana curve from edhrec json api as recommended mana curve
- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken


