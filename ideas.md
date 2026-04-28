# Ideas

- EDHREC Recommendations and trends
  - EDHREC recommendations (https://json.edhrec.com/commanders/<commander>.json).
  - Load this json once someone creates a commander deck we dont already got the edhrec-json data for.
  - If the data is older than 2 weeks update it again so do the request to the json api again and check out which cards are in the categories, otherwise take the data from a local cache we have for these.
  - utilize edhrec commander json api to get cards that are used in decks quite often f.e. `https://json.edhrec.com/pages/commanders/ms-bumbleflower.json` outputs `bumbleflower.json`
  - check out the key `panels.combocount` and parse the cards from there they are very good for this commander since they build a combo
  - in `container.json_dict.cardlists` you find an array of categories they are marked via `container.json_dict.cardlists[index].tag`
    - the categories are:
    - `new cards` (nice to look out for cards from a new set)
    - `high synergy` (most important cards, these are the bangers)
    - `topcards` (also bangers)
    - `game changers` (only relevant for bracket 3 and 4)
    - `creaturese`
    - `isntants`
    - `sourceries`
    - `utility artifacts`
    - `enchantments`
    - `planeswalker`
    - `utilitylands`
    - `manaartifacts` (Ramp)
    - `lands`
  - for these categories we need to find the corresponding card in our database and show it also in the corresponding deck building pages
- for edhrec recommendations there should be a new slider in preferences named (used in other decks) it should be heavy in weight by default because this is a very nice good metric of good cards

## 3 Optional nice to have

- Take the mana curve from edhrec json api as recommended mana curve
- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Collection sharing / import from other users
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- Checkout performance, is there steps we can improve/quicken
- EDHREC Recommendations and trends
  - EDHREC recommendations (json.edhrec.com/commanders/<commander>.json) Update it new if the data is older than 2 weeks, otherwise take the data from a local cache we have for these.
  - utilize edhrec commander json api to get cards that are used in decks quite often f.e. `https://json.edhrec.com/pages/commanders/ms-bumbleflower.json` outputs `bumbleflower.json`