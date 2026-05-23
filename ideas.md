# Next Features

- migrate all agents to pydantic ai

- deck optimization. simulate 1k first 4 turns to optimize a current deck.
  - use case: we have bad metrics in screw rate draw etc and we need more consistency
  - there is a button that changes cards in the deck and runs new simulation and then returns significant improvemnt on simulation results f.e. when changing these cards to these, the metrics move from xxx to yyy.

card search bar in expandle deck view on build/simulation page should match the card search bar for cards in the deck. Can we maybe merge them together as one so it applies the filter and shows the card in search and if we add it, it is already filtered and we see the card in the deck list from styling, it should rather have teh style from the search bar rather that the search bar for adding cards