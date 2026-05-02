# Ideas

⏺ Three I'd rank highest before a real-world test:

  Deck import from Moxfield/Archidekt URL. Most players at a game store already have a deck list somewhere. Asking them to build from scratch in your app to evaluate it is a tall order — letting them
  paste a Moxfield URL and instantly see your suggestions on their deck is the killer demo. Backend already has the Moxfield top-decks fetcher, so the deck-detail JSON path is short. Tradeoff: parser edge
   cases (sideboard, partner, double-faced names).

  Mobile/responsive pass + in-app feedback button. Game store users will pull this up on phones at the table. The build wizard's grid + filter dropdown work on desktop; haven't seen them on a 390px
  viewport. Bundle this with a small "Send feedback" button that writes to a feedback table — you'll get more honest signal than asking after the session. Tradeoff: low-glamour work, but cuts the
  highest-probability "this is broken" first impressions.

  Onboarding: pick a commander → instant sample deck. Right now first-time UX is empty list → "create deck" → describe agent → multi-stage wizard. That's a lot of trust to ask for. A "Start here" path
  that takes a commander and produces a draft deck (using your existing build pipeline run end-to-end automatically, then drop the user into the wizard mid-flow) makes the magic visible in 30 seconds.
  Tradeoff: the auto-run might surface lower-quality picks than guided stages — risk it ships a weak first impression if any stage produces noise.

## Optional nice to have
- Take the mana curve from edhrec json api as recommended mana curve
- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken
- Moxfield most liked decks
  - Commander => moxfield id
  - moxfield_id => top 5 decks most liked
  - Cards in top 5 => Add to card suggestions
  - New moxfield used_decks slider
