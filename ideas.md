# Ideas
- Ramp count does not change when adding cards in ramp/interaction/draw/theme/utility section
- Add Filter Values like Sourcery artifacts create f.e.
- Load more button in tabs should not return back to top instead stay at same hight in the list and append to the bottom
- Only show basic Lands in COmmander identity f.e. dont show islands for black/green commander
## 3 Optional nice to have

- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Collection sharing / import from other users
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken
- EDHREC Recommendations and trends
  - EDHREC recommendations (json.edhrec.com/commanders/<commander>.json) Update it new if the data is older than 2 weeks, otherwise take the data from a local cache we have for these.
  - utilize edhrec commander json api to get cards that are used in decks quite often f.e. `https://json.edhrec.com/pages/commanders/ms-bumbleflower.json` outputs `bumbleflower.json`