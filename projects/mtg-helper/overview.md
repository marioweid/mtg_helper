# Project overview

MTG Helper is a Commander deck workspace with local card search, staged building,
AI-assisted strategy and card advice, collections, planned changes, and goldfishing.
See the [README](../../README.md) for features, screenshots, and development entry points.

## Current scope

- Google sign-in with account-scoped decks and collections.
- Commander/partner selection, deck imports, and Moxfield-compatible exports.
- A deterministic stage builder plus a separate tool-using AI coach.
- Physical deck cards kept separate from pending additions/cuts and revision history.
- Collection ownership, price filters, Cardmarket shopping lists, and mana/playtest tools.
- Experimental released-card advice and an independently gated source-backed Discover pilot.

Account preference learning, cross-deck feedback ranking, and persistent Coach memory
are retired. Their stored data is retained, not used to personalize current advice.
The Preferences page is a placeholder, not a preference editor.

## Limits

AI advice is unverified; local identity and eligibility checks do not prove Magic rules
interpretations or strategic fit. Discover is default off and does not assess physical-deck
interactions. New Cards assesses the physical list but excludes previews and unresolved releases.
See the [remaining work](roadmap.md) and individual pilot contracts before extending either.
