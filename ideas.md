# Ideas

Mobile/responsive pass + in-app feedback button. Game store users will pull this up on phones at the table. The build wizard's grid + filter dropdown work on desktop; haven't seen them on a 390px
viewport. Bundle this with a small "Send feedback" button that writes to a feedback table — you'll get more honest signal than asking after the session. Tradeoff: low-glamour work, but cuts the
highest-probability "this is broken" first impressions.

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
