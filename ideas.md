# Ideas

1. Load more button does not load more after a couple of loads
2. When adding cards i dont see "Transcendent Envoy" in any category when building the commander "Ellivere of the Wild Court" even though the rank 6 most liked deck (https://moxfield.com/decks/LoNP_62hB0m0qJ97tCp8xw) has the card. Why is it like this. When we deal with moxfield/edhrec cards and the reason why its not shown is that we can put it in a category, we can just put all those cards in the theme section.
3. Can we improve card parsing so that cards can be more reliable be categorized to one of the specific categories and also the keywords etc. are better matched.
4. Total Card count not shown in deck builder. If it fits, we can als ouse an LLm here since the parsing is one done once and than only delta for new sets so cost are ok for this one.
5. Quick view in deckbuilder category that shows total cards and the cards in the current category (except banger)
6. Combo Section and also if a card has a lot of combo potential show combos with that card

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
