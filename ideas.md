# Ideas

## 3 Optional nice to have

- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Collection sharing / import from other users
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken
- EDHREC Recommendations and trends
  - EDHREC recommendations (json.edhrec.com/commanders/<commander>.json) Update it new if the data is older than 2 weeks, otherwise take the data from a local cache we have for these.
  - utilize edhrec commander json api to get cards that are used in decks quite often f.e. `https://json.edhrec.com/pages/commanders/ms-bumbleflower.json` outputs `bumbleflower.json`