# Next Features

- Bild steps should be:
  - theme: no target (also contains old utility and bangers)
  - Ramp: 12
  - draw: 12
  - interaction: 12
    - this is protection
    - utility
    - removale
    - counter spells
    - board wipes
    - etc.
  - Lands: 38
- Tags can be migrated from the all old ones to the new interaction one and the pipeline should tag with the new one from now on, no backward compatibility needed

- migrate all agents to pydantic ai

- deck optimization. simulate 1k first 4 turns to optimize a current deck.
  - use case: we have bad metrics in screw rate draw etc and we need more consistency
  - there is a button that changes cards in the deck and runs new simulation and then returns significant improvemnt on simulation results f.e. when changing these cards to these, the metrics move from xxx to yyy.
