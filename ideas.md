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

  UI redesign ideas (pick one big move)

  - Visual card-grid deck view (Moxfield style) — stacked image columns by type. Current list works but enthusiasts shop visually.
  - Bottom command bar — sticky Build · Chat · Stats · Export · Cuts instead of buttons scattered through header.
  - Drag-and-drop categories — move card between categories by drag; cut by drag-off.

  My recommendation if you want one to start:
  - Goldfish playtest + health scorecard combo. Both rank highest on "thing enthusiasts actually use during deck tuning", reuse data you already have, no new backend integrations.

Mobile/responsive pass + in-app feedback button. Game store users will pull this up on phones at the table. The build wizard's grid + filter dropdown work on desktop; haven't seen them on a 390px
viewport. Bundle this with a small "Send feedback" button that writes to a feedback table — you'll get more honest signal than asking after the session. Tradeoff: low-glamour work, but cuts the
highest-probability "this is broken" first impressions.

## Optional nice to have

- Take the mana curve from edhrec json api as recommended mana curve
- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken


