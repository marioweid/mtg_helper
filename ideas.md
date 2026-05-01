# Ideas
- Logik to parse moxfield top 10 decks when creating a new commander (After 4 weeks the top 10 is reparsed again)
- More filters like (equipment, Auras, etc. cummon types so that we can filter for those sepcific things f.e. ramp equipments)

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
