## 1 Fix Bugs
- Switch Embedding and Model to Gemini (from OpenAI)

## 2 Deploy to GCP
- Proper user management
- Deploy to GCP
- Switch openai to gemini for better usage costs monitoring


## 3 Optional nice to have

- Performance beyond ~10k-card collections (HasIdCondition cost in Qdrant)
- Collection sharing / import from other users
- Multi-format support beyond Moxfield CSV (Archidekt, MTGGoldfish)
- Price aggregation across printings
- EDHREC recommendations (json.edhrec.com/commanders/<commander>.json) Update it new if the data is older than 2 weeks, otherwise take the data from a local cache we have for these.
- Checkout performance, is there steps we can improve/quicken
