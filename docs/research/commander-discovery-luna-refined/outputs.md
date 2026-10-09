# Actual Luna refined-pipeline outputs

All six completed responses are archived in `results.json`. This rendering does not repair
schema-valid nonsense, failed quotations or rules interpretations. These are regressions,
not holdouts; automated grounding is not semantic accuracy.

## Meren — plan

6.89 seconds; estimated $0.00075805.

```json
{
  "intents": [
    "Accumulate experience through repeatable sacrifice outlets and disposable creatures.",
    "Reuse enters-the-battlefield and dies-triggered effects for removal, ramp, card advantage, and graveyard control.",
    "Support Meren with self-mill, creature tutors, mana acceleration, and ways to protect or recover the engine.",
    "Investigate timing and rules distinctions between dying, entering, returning, and triggered abilities.],",
    "searches [{",
    "purpose",
    "oracle_text_any",
    "oracle_text_all"
  ],
  "searches": [],
  "named_cards": [],
  "uncertainties": [],
  "rule_searches": []
}
```

## Saheeli — plan

15.57 seconds; estimated $0.00199650.

```json
{
  "intents": [
    "Build a high-density Temur artifact shell that steadily produces energy through artifact and Artificer casts.",
    "Use energy on Saheeli’s temporary 5/5 copies, prioritizing permanents with strong entry, activated, attack, or death value.",
    "Exploit haste and temporary combat bodies with attack triggers, sacrifice value, and ways to preserve or multiply token value.",
    "Include resilient copy targets and artifact engines so the deck remains functional when Saheeli is unavailable."
  ],
  "searches": [
    {
      "purpose": "Find repeatable energy production attached to artifacts or permanents.",
      "oracle_text_all": [
        "energy counter"
      ],
      "oracle_text_any": [],
      "type_line_any": [
        "Artifact"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find spells that reward casting artifacts or Artificers with energy.",
      "oracle_text_all": [
        "energy counter"
      ],
      "oracle_text_any": [
        "Whenever you cast",
        "Whenever you cast an artifact"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find useful permanents whose entry triggers become powerful temporary copies.",
      "oracle_text_all": [
        "enters the battlefield"
      ],
      "oracle_text_any": [
        "draw",
        "create",
        "destroy",
        "return"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": 3.0,
      "mana_value_max": null
    },
    {
      "purpose": "Find permanents that directly support copying or multiplying tokens.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "copy of",
        "token you control",
        "tokens you control"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find combat payoffs for Saheeli’s hasty temporary copies.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "attacks",
        "combat damage",
        "whenever a creature you control attacks"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find artifacts and creatures that turn temporary deaths or sacrifices into resources.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "sacrifice",
        "dies",
        "is put into a graveyard from the battlefield"
      ],
      "type_line_any": [
        "Artifact",
        "Creature"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find artifact-based mana and card-advantage engines that are good Saheeli copy targets.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "Add",
        "draw a card",
        "draw cards"
      ],
      "type_line_any": [
        "Artifact"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": 2.0,
      "mana_value_max": null
    },
    {
      "purpose": "Find ways to retain value from tokens or exploit their temporary existence.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "exile",
        "sacrifice",
        "create a token"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    }
  ],
  "named_cards": [
    "Aetherworks Marvel",
    "Decoction Module",
    "Fabrication Module",
    "Era of Innovation",
    "Whirler Virtuoso",
    "Gonti’s Aether Heart",
    "Saheeli, Sublime Artificer",
    "Brudiclad, Telchor Engineer",
    "Panharmonicon",
    "Lithoform Engine",
    "Mimic Vat",
    "Reckless Fireweaver"
  ],
  "uncertainties": [
    "Verify which energy engines are legal in Temur and whether their output is fast enough to support paying three energy every combat.",
    "Confirm how copied permanents’ enters-the-battlefield abilities, replacement effects, loyalty abilities, and delayed sacrifice interact with Saheeli’s copy effect.",
    "Check whether token-copy multipliers preserve Saheeli’s specified 5/5, artifact, haste, and sacrifice modifications.",
    "Determine whether death-trigger and sacrifice outlets can meaningfully convert the temporary token into value before the delayed sacrifice."
  ],
  "rule_searches": [
    {
      "purpose": "Clarify the comprehensive rules for energy counters and paying energy costs.",
      "text_all": [
        "energy counter"
      ],
      "text_any": [],
      "cursor": null
    },
    {
      "purpose": "Clarify copy effects, copied characteristics, and exceptions such as becoming a 5/5 artifact creature.",
      "text_all": [
        "copy effect"
      ],
      "text_any": [
        "except"
      ],
      "cursor": null
    },
    {
      "purpose": "Clarify token creation and what characteristics a token copy receives.",
      "text_all": [
        "token"
      ],
      "text_any": [
        "copy"
      ],
      "cursor": null
    },
    {
      "purpose": "Clarify when enters-the-battlefield abilities trigger on copied permanents.",
      "text_all": [
        "enters the battlefield"
      ],
      "text_any": [
        "copy"
      ],
      "cursor": null
    },
    {
      "purpose": "Clarify the timing of Saheeli’s delayed sacrifice at the next end step.",
      "text_all": [
        "beginning of the next end step"
      ],
      "text_any": [],
      "cursor": null
    },
    {
      "purpose": "Clarify haste and attacking with a temporary copied creature created during combat setup.",
      "text_all": [
        "haste"
      ],
      "text_any": [
        "summoning sickness",
        "attack"
      ],
      "cursor": null
    }
  ]
}
```

## Meren — revise

12.93 seconds; estimated $0.00185390.

```json
{
  "intents": [
    "Build a sacrifice engine that reliably creates experience counters while converting expendable creatures into cards, mana, removal, or board control.",
    "Reuse creatures with strong enters-the-battlefield, dies, or sacrifice abilities through Meren and other recursion effects.",
    "Fill the graveyard and selectively find creatures whose mana values align with Meren's end-step recursion threshold.",
    "Protect the recursion engine and retain value when creatures are exiled, returned to hand, or otherwise unavailable.",
    "Investigate exact rules for dies triggers, returning cards to the battlefield, triggered-ability timing, and sacrifice costs."
  ],
  "searches": [
    {
      "purpose": "Repeatable sacrifice outlets that do not require a creature to tap",
      "oracle_text_all": [
        "sacrifice a creature"
      ],
      "oracle_text_any": [],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Sacrifice outlets that also produce mana or another reusable resource",
      "oracle_text_all": [
        "sacrifice a creature"
      ],
      "oracle_text_any": [
        "Add",
        "draw a card",
        "create a"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Creatures that reward their own or another creature's death with cards, mana, or tokens",
      "oracle_text_all": [
        "dies"
      ],
      "oracle_text_any": [
        "draw a card",
        "Add",
        "create a token",
        "each opponent"
      ],
      "type_line_any": [
        "Creature"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Creature-based removal and interaction that can be repeatedly returned",
      "oracle_text_all": [
        "enters the battlefield"
      ],
      "oracle_text_any": [
        "destroy target",
        "exile target",
        "return target",
        "-1/-1"
      ],
      "type_line_any": [
        "Creature"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Creatures that stock the graveyard or find creatures for reliable recursion",
      "oracle_text_all": [],
      "oracle_text_any": [
        "mill",
        "put a card from your library into your graveyard",
        "search your library for a creature card",
        "return a creature card from your graveyard"
      ],
      "type_line_any": [
        "Creature"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Ways to protect Meren or a creature-based engine from removal",
      "oracle_text_all": [],
      "oracle_text_any": [
        "hexproof",
        "indestructible",
        "protection from",
        "regenerate"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Additional recursion that returns creatures to the battlefield or hand",
      "oracle_text_all": [],
      "oracle_text_any": [
        "return target creature card from your graveyard to the battlefield",
        "return a creature card from your graveyard to your hand"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Low-mana-value utility creatures suited to repeated Meren recursion",
      "oracle_text_all": [
        "enters the battlefield"
      ],
      "oracle_text_any": [],
      "type_line_any": [
        "Creature"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": 1.0,
      "mana_value_max": 3.0
    }
  ],
  "named_cards": [
    "Viscera Seer",
    "Carrion Feeder",
    "Ashnod's Altar",
    "Phyrexian Altar",
    "Blood Artist",
    "Zulaport Cutthroat",
    "Skullclamp",
    "Sakura-Tribe Elder",
    "Eternal Witness",
    "Reclamation Sage",
    "Shriekmaw",
    "Plaguecrafter"
  ],
  "uncertainties": [
    "The exact available card pool and wording for sacrifice outlets, death-payoff creatures, and recursion spells must be verified locally.",
    "Meren's end-step ability targets a creature card before checking its mana value; replacement effects, exile effects, and graveyard changes may affect whether the target remains available.",
    "Whether a creature's ability triggers on entering, dying, being sacrificed, or leaving the battlefield must be checked from its exact Oracle text.",
    "Potential loops or high-power interactions are not being excluded because no combo, budget, or bracket restrictions were supplied."
  ],
  "rule_searches": [
    {
      "purpose": "Verify the rules definition and consequences of a creature dying.",
      "text_all": [
        "dies"
      ],
      "text_any": [],
      "cursor": null
    },
    {
      "purpose": "Clarify sacrifice as a cost and when a sacrificed creature is put into the graveyard.",
      "text_all": [
        "sacrifice"
      ],
      "text_any": [],
      "cursor": null
    },
    {
      "purpose": "Check how triggered abilities are put on the stack and resolve after sacrifice or death events.",
      "text_all": [
        "triggered ability"
      ],
      "text_any": [
        "stack"
      ],
      "cursor": null
    },
    {
      "purpose": "Verify how returning a creature card from a graveyard to the battlefield works.",
      "text_all": [
        "return"
      ],
      "text_any": [
        "battlefield"
      ],
      "cursor": null
    },
    {
      "purpose": "Clarify triggered abilities that trigger when a creature enters the battlefield.",
      "text_all": [
        "enters the battlefield"
      ],
      "text_any": [],
      "cursor": null
    },
    {
      "purpose": "Clarify last-known information for death triggers and abilities of creatures that leave the battlefield.",
      "text_all": [
        "last known information"
      ],
      "text_any": [],
      "cursor": null
    }
  ]
}
```

## Saheeli — revise

13.73 seconds; estimated $0.00420585.

```json
{
  "intents": [
    "Prioritize artifact and Artificer density so Saheeli reliably accumulates three energy before combat.",
    "Use repeatable energy sources and artifact permanents with tap abilities as high-value copy targets.",
    "Favor copied permanents with entry triggers, attack triggers, or sacrifice/death value; Saheeli’s copy enters with the target’s copiable abilities, while her 5/5 and haste modifications remain part of the copy.",
    "Exploit combat damage and attack triggers, recognizing that the token’s haste permits attacking immediately but its delayed sacrifice occurs at the next end step.",
    "Use sacrifice outlets and death-trigger payoffs to convert Saheeli’s temporary copy into value before the delayed sacrifice.",
    "Energy production may be slower than one Saheeli activation per turn; include ordinary artifact ramp, draw, and resilient engines rather than relying exclusively on energy."
  ],
  "searches": [
    {
      "purpose": "Find artifacts that produce energy when they enter or through repeatable activated abilities.",
      "oracle_text_all": [
        "energy"
      ],
      "oracle_text_any": [
        "you get",
        "energy counters"
      ],
      "type_line_any": [
        "Artifact"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find permanents that produce energy when an artifact or creature enters, supporting repeated artifact deployment.",
      "oracle_text_all": [
        "energy"
      ],
      "oracle_text_any": [
        "enters",
        "enters the battlefield"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find high-impact permanents with entry abilities suitable for Saheeli copies.",
      "oracle_text_all": [
        "enters"
      ],
      "oracle_text_any": [
        "draw",
        "create",
        "destroy",
        "return",
        "search"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": 3.0,
      "mana_value_max": null
    },
    {
      "purpose": "Find artifact permanents with repeatable mana, draw, or resource-producing abilities.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "Add",
        "draw a card",
        "draw cards",
        "create"
      ],
      "type_line_any": [
        "Artifact"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": 2.0,
      "mana_value_max": null
    },
    {
      "purpose": "Find attack or combat-damage payoffs that reward Saheeli’s hasty temporary copies.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "Whenever this creature attacks",
        "Whenever a creature you control attacks",
        "combat damage"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find sacrifice outlets and death payoffs that can monetize Saheeli’s token before its delayed sacrifice.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "sacrifice",
        "dies",
        "is put into a graveyard"
      ],
      "type_line_any": [
        "Artifact",
        "Creature",
        "Enchantment"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find permanents that copy creatures or tokens, including additional temporary bodies and copy synergies.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "copy"
      ],
      "type_line_any": [
        "Artifact",
        "Creature",
        "Enchantment"
      ],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    },
    {
      "purpose": "Find artifact and Artificer spells that improve Saheeli’s energy generation and provide standalone value.",
      "oracle_text_all": [],
      "oracle_text_any": [
        "artifact",
        "Artificer"
      ],
      "type_line_any": [],
      "keywords_any": [],
      "mana_cost_all": [],
      "mana_value_min": null,
      "mana_value_max": null
    }
  ],
  "named_cards": [
    "Aetherworks Marvel",
    "Decoction Module",
    "Fabrication Module",
    "Era of Innovation",
    "Whirler Virtuoso",
    "Dynavolt Tower",
    "Bespoke Battlewagon",
    "The Motherlode, Excavator",
    "Saheeli, Sublime Artificer",
    "Panharmonicon",
    "Mimic Vat",
    "Reckless Fireweaver"
  ],
  "uncertainties": [
    "The observed energy search is truncated, so additional legal Temur engines remain undiscovered; confirm their exact production rate and whether they require artifacts, creatures, or other spells.",
    "The copy rules confirm that Saheeli’s exceptions become copiable values and that enters-the-battlefield choices are made anew, but the practical value of any target still depends on its exact triggered ability and costs.",
    "A token sacrifice outlet may sacrifice the copy before the delayed trigger; verify whether each outlet is usable without spending more resources than the copy produces.",
    "Token-copy multipliers and effects that create multiple tokens may interact with Saheeli’s explicit 5/5, artifact, haste, and sacrifice exceptions in card-specific ways; do not assume they preserve every modification."
  ],
  "rule_searches": [
    {
      "purpose": "Continue the token and copy rules search to inspect later entries on token characteristics and copy creation.",
      "text_all": [
        "token"
      ],
      "text_any": [
        "copy"
      ],
      "cursor": "G:Offspring"
    },
    {
      "purpose": "Continue the enters-the-battlefield and copy rules search for triggering details after the returned page.",
      "text_all": [
        "enters the battlefield"
      ],
      "text_any": [
        "copy"
      ],
      "cursor": "707.4"
    },
    {
      "purpose": "Continue the delayed-sacrifice timing search for the end-step rules and delayed triggered abilities.",
      "text_all": [
        "beginning of the next end step"
      ],
      "text_any": [],
      "cursor": "702.185a"
    },
    {
      "purpose": "Investigate sacrifice timing and whether sacrificing a temporary token before a delayed sacrifice changes the delayed trigger’s result.",
      "text_all": [
        "sacrifice"
      ],
      "text_any": [
        "delayed",
        "triggered"
      ],
      "cursor": null
    }
  ]
}
```

## Meren — review

48.10 seconds; estimated $0.01113530.

Grounded rows: 63/64; complete validation: False.

### Actual rankings

1. **Viscera Seer** (C17, core; ranking valid: True)
   A zero-mana sacrifice outlet repeatedly triggers Meren, scries away unwanted draws, and lets ETB creatures be timed for recursion.
   Caveat: Scry 1 is selection rather than card advantage.
2. **Ashnod's Altar** (C14, core; ranking valid: True)
   A free sacrifice outlet converts every creature into two mana and an experience counter, enabling repeated death-trigger and recursion turns.
   Caveat: Produces colorless mana and requires creatures worth sacrificing.
3. **Phyrexian Altar** (C54, core; ranking valid: True)
   A free sacrifice outlet produces colored mana, enabling Meren recursions and multiplying death-trigger value without requiring a tap.
   Caveat: Mana production is one mana per creature and needs creatures to fuel it.
4. **Stitcher's Supplier** (C16, core; ranking valid: True)
   One-mana creature that mills on entry and death fills the graveyard and naturally rewards sacrifice, making Meren's threshold and targets reliable.
   Caveat: Mill can lose important cards and does not select among them.
5. **Reclamation Sage** (C08, core; ranking valid: True)
   Repeatable ETB artifact/enchantment removal is excellent with Meren; sacrificing and returning it repeatedly also builds experience.
   Caveat: Targets only artifacts or enchantments and requires a legal target.
6. **Plaguecrafter** (C20, core; ranking valid: True)
   Its ETB forces each player to sacrifice or discard, creating immediate interaction; Meren can repeatedly return it for attrition and experience support.
   Caveat: Symmetrical and ineffective against players with expendable boards or empty hands.
7. **Shriekmaw** (C57, core; ranking valid: True)
   Evoke supplies cheap ETB creature removal and immediate sacrifice, producing experience; Meren can repeatedly return it for removal loops.
   Caveat: Only destroys nonartifact, nonblack creatures and evoke sacrifices it on entry.
8. **Eternal Witness** (C45, core; ranking valid: True)
   Recurs any graveyard card to hand on ETB, letting Meren repeatedly reuse key creatures, sacrifice outlets, or interaction while itself is a strong target.
   Caveat: Returns cards to hand rather than directly to the battlefield.
9. **Sakura-Tribe Elder** (C37, core; ranking valid: True)
   Sacrifices itself for land ramp and an experience counter, then Meren can recur it to repeat landfall-ready acceleration.
   Caveat: Only finds basic lands and puts them onto the battlefield tapped.
10. **Blood Artist** (C29, core; ranking valid: True)
   Turns every creature death into life loss and life gain, making Meren's repeated sacrifice loops into a win condition and stabilizing races.
   Caveat: Targets only one player per trigger and has zero toughness.
11. **Zulaport Cutthroat** (C62, core; ranking valid: True)
   A low-cost death payoff drains every opponent and gains life, converting repeated Meren sacrifices into scalable board-control payoff and a win condition.
   Caveat: Its one toughness makes it vulnerable and it requires the creature to remain on the battlefield.
12. **Grim Haruspex** (C32, core; ranking valid: True)
   Draws for each nontoken creature death, directly converting Meren sacrifices into cards and remaining a useful low-cost recursive creature.
   Caveat: Does not reward token deaths and costs three mana.
13. **Morbid Opportunist** (C24, core; ranking valid: True)
   Draws once each turn whenever creatures die, turning Meren's sacrifice loop into steady cards while also benefiting from opponents' deaths.
   Caveat: Only triggers once per turn and excludes no creature type beyond its wording's event.
14. **Spore Frog** (C34, core; ranking valid: True)
   A one-mana creature is a repeatable sacrifice that prevents combat damage; Meren can recur it each end step for recurring battlefield control.
   Caveat: Only prevents combat damage and needs a sacrifice outlet effect timing plan.
15. **Yawgmoth, Thran Physician** (C48, core; ranking valid: True)
   A sacrifice outlet that draws cards and supplies removal counters directly advances Meren's engine; proliferate can also grow experience counters.
   Caveat: Costs one life per sacrifice and cannot sacrifice itself.

### Every assessment (including unranked/failed)

#### C00 — Galvanic Juggernaut (weak)

Untapping after deaths is incidental; it neither sacrifices creatures nor rewards recursion, while forced attacks conflict with a value-engine plan.

Caveat: Useful only with a combat-focused artifact package.

Evidence errors: none

Source C00:
```text
Whenever another creature dies, untap this creature.
```

#### C01 — Drivnod, Carnage Dominus (support)

Doubles Meren's death-triggered experience and other death triggers; its graveyard exile cost competes with recursion targets.

Caveat: Requires five mana and three expendable creature cards in the graveyard.

Evidence errors: none

Source C01:
```text
that ability triggers an additional time.
```

#### C02 — Ground Seal (weak)

The cantrip is useful, but stopping all graveyard targets shuts off Meren and most recursion, including its own strategic plan.

Caveat: Consider only in a graveyard-hate side direction.

Evidence errors: none

Source C02:
```text
Cards in graveyards can't be the targets of spells or abilities.
```

#### C03 — Soulcoil Viper (support)

A creature that sacrifices itself into immediate recursion can generate experience and reuse a creature ETB; finality prevents that creature's later return after dying.

Caveat: Sorcery timing and {B} activation limit flexibility.

Evidence errors: none

Source C03:
```text
Sacrifice this creature: Return target creature card from your graveyard to the battlefield with a finality counter on it.
```

#### C04 — Kitchen Imp (weak)

Madness can place it in the graveyard, but it offers no ETB, death, sacrifice, or recursion value for Meren.

Caveat: Needs a dedicated discard package to become relevant.

Evidence errors: none

Source C04:
```text
Madness {B}
```

#### C05 — Transmogrant Altar (support)

Provides a sacrifice outlet, burst mana, and Zombie production; repeated sacrifices create experience and can fund recursion turns.

Caveat: Both abilities tap, and the mana ability produces colorless only.

Evidence errors: none

Source C05:
```text
Sacrifice a creature: Add {C}{C}{C}.
```

#### C06 — The Vision (weak)

Draws from noncreature spells and supplies combat protection, but does not interact with sacrificing, dying, or creature recursion.

Caveat: Requires a noncreature-spell-heavy build.

Evidence errors: none

Source C06:
```text
Whenever you cast a noncreature spell
```

#### C07 — Harvester Troll (support)

Its ETB converts an expendable creature or land into a larger body, creating a sacrifice event and a reasonable Meren recursion target.

Caveat: Four mana and no further ETB or death value make it modest.

Evidence errors: none

Source C07:
```text
you may sacrifice a creature or land.
```

#### C08 — Reclamation Sage (core)

Repeatable ETB artifact/enchantment removal is excellent with Meren; sacrificing and returning it repeatedly also builds experience.

Caveat: Targets only artifacts or enchantments and requires a legal target.

Evidence errors: none

Source C08:
```text
When this creature enters, you may destroy target artifact or enchantment.
```

#### C09 — Satyr Wayfinder (support)

Stocks the graveyard while finding a land, and its low mana value makes it easy for Meren to recur for repeated selection and sacrifice value.

Caveat: Only four cards are milled and the land is merely put into hand.

Evidence errors: none

Source C09:
```text
reveal the top four cards of your library
```

#### C10 — Tunnel Rats (weak)

Self-recursion supplies a recurring body, but its high activation cost lacks an ETB, death payoff, or sacrifice outlet.

Caveat: Needs abundant mana and a Rat-focused package.

Evidence errors: none

Source C10:
```text
Return this card from your graveyard to the battlefield tapped.
```

#### C11 — Chrome Dome (weak)

Artifact-copy tokens can create temporary ETB value, but the card has no sacrifice or death interaction and costs heavily to activate.

Caveat: Needs a high-value artifact package.

Evidence errors: none

Source C11:
```text
Create a token that's a copy of another target artifact you control.
```

#### C12 — Dokuchi Silencer (conditional)

Discarding creatures enables graveyard setup while its combat trigger removes opposing creatures; ninjutsu can reuse an attacker, but it is not a sacrifice engine.

Caveat: Requires reliable unblocked attackers and a discard package.

Evidence errors: none

Source C12:
```text
you may discard a creature card. When you do, destroy target creature or planeswalker
```

#### C13 — Roadkill Rodney (conditional)

Squad supplies multiple bodies for sacrifice and deathtouch improves combat, while death recursion can rebuild copies only indirectly.

Caveat: Needs substantial extra mana and combat access.

Evidence errors: none

Source C13:
```text
When this creature enters, create that many tokens that are copies of it.
```

#### C14 — Ashnod's Altar (core)

A free sacrifice outlet converts every creature into two mana and an experience counter, enabling repeated death-trigger and recursion turns.

Caveat: Produces colorless mana and requires creatures worth sacrificing.

Evidence errors: none

Source C14:
```text
Sacrifice a creature: Add {C}{C}.
```

#### C15 — Woodland Bellower (support)

A large recursive body tutors a low-cost green utility creature, then Meren can reuse both ETBs for sustained board value.

Caveat: Six mana and the tutored creature must be nonlegendary, green, and mana value three or less.

Evidence errors: none

Source C15:
```text
search your library for a nonlegendary green creature card with mana value 3 or less
```

#### C16 — Stitcher's Supplier (core)

One-mana creature that mills on entry and death fills the graveyard and naturally rewards sacrifice, making Meren's threshold and targets reliable.

Caveat: Mill can lose important cards and does not select among them.

Evidence errors: none

Source C16:
```text
When this creature enters or dies, mill three cards.
```

#### C17 — Viscera Seer (core)

A zero-mana sacrifice outlet repeatedly triggers Meren, scries away unwanted draws, and lets ETB creatures be timed for recursion.

Caveat: Scry 1 is selection rather than card advantage.

Evidence errors: none

Source C17:
```text
Sacrifice a creature: Scry 1.
```

#### C18 — Plagued Rusalka (support)

Provides a repeatable sacrifice outlet plus creature shrinkage, generating experience while functioning as low-cost interaction against small creatures.

Caveat: Requires {B} per activation and only gives -1/-1.

Evidence errors: none

Source C18:
```text
{B}, Sacrifice a creature: Target creature gets -1/-1 until end of turn.
```

#### C19 — The Dawning Archaic (weak)

Its graveyard spell-casting attack ability is unrelated to creature recursion and its ten-mana value is poor for Meren's curve.

Caveat: Needs a dedicated instant-sorcery graveyard deck.

Evidence errors: none

Source C19:
```text
Whenever The Dawning Archaic attacks, you may cast target instant or sorcery card from your graveyard
```

#### C20 — Plaguecrafter (core)

Its ETB forces each player to sacrifice or discard, creating immediate interaction; Meren can repeatedly return it for attrition and experience support.

Caveat: Symmetrical and ineffective against players with expendable boards or empty hands.

Evidence errors: none

Source C20:
```text
each player sacrifices a creature or planeswalker of their choice.
```

#### C21 — The Masamune (conditional)

Can double death triggers on an equipped creature, potentially multiplying value, but it is not itself a sacrifice outlet and needs combat-equipment support.

Caveat: Requires equip mana and a creature with a relevant death trigger.

Evidence errors: none

Source C21:
```text
that ability triggers an additional time.
```

#### C22 — Carrion Feeder (core)

Free sacrifice outlet grows while converting disposable creatures into experience, and its Zombie type supports tribal tutors or recursion packages.

Caveat: Cannot block and supplies no direct card or mana advantage.

Evidence errors: none

Source C22:
```text
Sacrifice a creature: Put a +1/+1 counter on this creature.
```

#### C23 — Lobelia Sackville-Baggins (support)

Flash graveyard hate and Treasure production answer an opponent's recent creature while providing mana for recursion and sacrifice turns.

Caveat: Targets only an opposing creature card put there from the battlefield this turn.

Evidence errors: none

Source C23:
```text
exile target creature card from an opponent's graveyard that was put there from the battlefield this turn
```

#### C24 — Morbid Opportunist (core)

Draws once each turn whenever creatures die, turning Meren's sacrifice loop into steady cards while also benefiting from opponents' deaths.

Caveat: Only triggers once per turn and excludes no creature type beyond its wording's event.

Evidence errors: none

Source C24:
```text
Whenever one or more other creatures die, draw a card.
```

#### C25 — Saheeli's Silverwing (weak)

A small flying body that only looks at an opponent's top card has no meaningful sacrifice, death, ETB value, or recursion payoff.

Caveat: Could fit a narrow information or artifact-creature package.

Evidence errors: none

Source C25:
```text
look at the top card of target opponent's library.
```

#### C26 — Harold and Bob, First Numens (support)

It returns itself after dying, creating repeated death and ETB-like land-mana utility while supplying a resilient sacrifice body.

Caveat: Its return changes it into an Aura and requires a Forest you control.

Evidence errors: none

Source C26:
```text
When Harold and Bob dies, if it was a creature, return it to the battlefield.
```

#### C27 — Contamination (conditional)

Turns recurring expendable creatures into a mana-denial lock, while Meren can replace the upkeep sacrifice and grow experience.

Caveat: Requires reliable creature recursion and can severely constrain your own nonblack mana.

Evidence errors: none

Source C27:
```text
At the beginning of your upkeep, sacrifice this enchantment unless you sacrifice a creature.
```

#### C28 — Driver of the Dead (support)

Sacrificing this four-mana creature returns a low-cost creature, creating a compact death-to-ETB chain for Meren's experience engine.

Caveat: The returned creature must have mana value two or less.

Evidence errors: none

Source C28:
```text
When this creature dies, return target creature card with mana value 2 or less from your graveyard to the battlefield.
```

#### C29 — Blood Artist (core)

Turns every creature death into life loss and life gain, making Meren's repeated sacrifice loops into a win condition and stabilizing races.

Caveat: Targets only one player per trigger and has zero toughness.

Evidence errors: none

Source C29:
```text
Whenever this creature or another creature dies, target player loses 1 life and you gain 1 life.
```

#### C30 — Popular Egotist (support)

Sacrifice protection preserves the creature while its sacrifice-triggered drain rewards every permanent sacrificed, including creatures used with Meren.

Caveat: Protection costs {1}{B}, taps the creature, and the drain is only one life.

Evidence errors: none

Source C30:
```text
Whenever you sacrifice a permanent, target opponent loses 1 life and you gain 1 life.
```

#### C31 — Cryptolith Fragment // Aurora of Emrakul (weak)

Mana production and eventual combat pressure are useful generally, but it lacks sacrifice, death, ETB, and recursion value.

Caveat: Needs a ramp or life-drain direction to justify inclusion.

Evidence errors: none

Source C31:
```text
{T}: Add one mana of any color.
```

#### C32 — Grim Haruspex (core)

Draws for each nontoken creature death, directly converting Meren sacrifices into cards and remaining a useful low-cost recursive creature.

Caveat: Does not reward token deaths and costs three mana.

Evidence errors: none

Source C32:
```text
Whenever another nontoken creature you control dies, draw a card.
```

#### C33 — Lich's Relic (conditional)

Cheap equipment can repeatedly remove creatures on entry and gives a recursive body more power, but requires an extra payment and equip package.

Caveat: The ETB removal costs {2} and equipment is otherwise modest.

Evidence errors: none

Source C33:
```text
for each opponent, destroy up to one target creature or planeswalker
```

#### C34 — Spore Frog (core)

A one-mana creature is a repeatable sacrifice that prevents combat damage; Meren can recur it each end step for recurring battlefield control.

Caveat: Only prevents combat damage and needs a sacrifice outlet effect timing plan.

Evidence errors: none

Source C34:
```text
Sacrifice this creature: Prevent all combat damage that would be dealt this turn.
```

#### C35 — Beast Whisperer (support)

Draws whenever you cast recurring creature spells, replenishing cards as Meren and other recursion engines deploy creatures.

Caveat: Requires four mana and triggers on casting, not creatures returned directly without being cast.

Evidence errors: none

Source C35:
```text
Whenever you cast a creature spell, draw a card.
```

#### C36 — Dowsing Shaman (weak)

Returns enchantments to hand, but the deck's primary recursion target is creatures and the activated ability is expensive and taps.

Caveat: Needs a meaningful enchantment package.

Evidence errors: none

Source C36:
```text
Return target enchantment card from your graveyard to your hand.
```

#### C37 — Sakura-Tribe Elder (core)

Sacrifices itself for land ramp and an experience counter, then Meren can recur it to repeat landfall-ready acceleration.

Caveat: Only finds basic lands and puts them onto the battlefield tapped.

Evidence errors: none

Source C37:
```text
Sacrifice this creature: Search your library for a basic land card
```

#### C38 — March of the World Ooze (weak)

A costly global creature transformation and token generation do not advance sacrifice recursion, and the 6/6 setting can erase useful small-body roles.

Caveat: Needs a token-heavy combat direction.

Evidence errors: none

Source C38:
```text
Creatures you control have base power and toughness 6/6
```

#### C39 — Insidious Fungus (support)

A one-mana creature sacrifices for artifact/enchantment removal or a card and land, providing flexible value that Meren can recur.

Caveat: Each mode requires {2}, and the land mode depends on having a land in hand.

Evidence errors: none

Source C39:
```text
{2}, Sacrifice this creature: Choose one
```

#### C40 — Grist, Voracious Larva // Grist, the Plague Swarm (conditional)

Milled cards and graveyard-entry triggers support recursion, while transformed Grist makes removal and creature copies; it needs a graveyard-focused package.

Caveat: Transforming requires a qualifying graveyard entry and paying {G}; planeswalker copying is delayed.

Evidence errors: none

Source C40:
```text
Whenever Grist or another creature you control enters, if it entered from your graveyard or you cast it from your graveyard
```

#### C41 — Sureshot Sower (weak)

Reach and discard-based flying removal provide narrow utility, but the card lacks sacrifice, death, ETB, and recursion value.

Caveat: Needs a discard outlet and a flying-heavy metagame.

Evidence errors: none

Source C41:
```text
Discard this card: Destroy target creature with flying.
```

#### C42 — Tethermage's Advantage (weak)

A temporary combat trick neither advances sacrifice nor recursion and has little value from Meren's creature-focused end-step ability.

Caveat: Useful only in a combat-protection direction.

Evidence errors: none

Source C42:
```text
Target creature gets +2/+2 and gains reach until end of turn.
```

#### C43 — Pyre of Heroes (conditional)

Sacrifices a creature to tutor a same-type creature, enabling chains and death triggers, but requires carefully built tribal curves and sorcery timing.

Caveat: Requires a matching creature type at exactly one higher mana value.

Evidence errors: none

Source C43:
```text
Sacrifice a creature: Search your library for a creature card that shares a creature type
```

#### C44 — Razorlash Transmogrant (weak)

Self-recursion supplies a body for sacrifice, but six mana is inefficient and the opponent-land condition is unreliable; it has no ETB value.

Caveat: Becomes cheaper only against the specified nonbasic-land board state.

Evidence errors: none

Source C44:
```text
Return this card from your graveyard to the battlefield with a +1/+1 counter on it.
```

#### C45 — Eternal Witness (core)

Recurs any graveyard card to hand on ETB, letting Meren repeatedly reuse key creatures, sacrifice outlets, or interaction while itself is a strong target.

Caveat: Returns cards to hand rather than directly to the battlefield.

Evidence errors: none

Source C45:
```text
return target card from your graveyard to your hand.
```

#### C46 — Twilight Diviner (conditional)

Surveil fills and filters the graveyard, while graveyard-entry creatures can create extra bodies for sacrifice and death triggers.

Caveat: Copy trigger is once per turn and only works with creatures entering or cast from graveyards.

Evidence errors: none

Source C46:
```text
Whenever one or more other creatures you control enter, if they entered or were cast from a graveyard
```

#### C47 — Solemn Simulacrum (support)

Provides a creature death trigger for a card and an ETB land, making it a reusable ramp-and-draw package when sacrificed and returned.

Caveat: Four mana and only searches basic lands.

Evidence errors: none

Source C47:
```text
When this creature dies, you may draw a card.
```

#### C48 — Yawgmoth, Thran Physician (core)

A sacrifice outlet that draws cards and supplies removal counters directly advances Meren's engine; proliferate can also grow experience counters.

Caveat: Costs one life per sacrifice and cannot sacrifice itself.

Evidence errors: none

Source C48:
```text
Pay 1 life, Sacrifice another creature: Put a -1/-1 counter on up to one target creature and draw a card.
```

#### C49 — Yahenni, Undying Partisan (support)

Free sacrifice outlet protects itself while opposing deaths grow it, creating experience and a resilient secondary threat.

Caveat: Its protection sacrifices another creature and it is legendary, limiting duplicates.

Evidence errors: none

Source C49:
```text
Sacrifice another creature: Yahenni gains indestructible until end of turn.
```

#### C50 — Gravestone Strider (support)

Provides limited fixing from the battlefield and graveyard hate from exile, while its exile cost can interfere with only selected recursion targets.

Caveat: Mana ability is once per turn and graveyard activation exiles the card itself.

Evidence errors: none

Source C50:
```text
{2}, Exile this card from your graveyard: Exile target card from a graveyard.
```

#### C51 — Black Carriage (weak)

Sacrifice untaps it only during upkeep, so it is neither a flexible outlet nor a meaningful death-value creature for Meren.

Caveat: Needs a combat-focused build and creatures available during upkeep.

Evidence errors: none

Source C51:
```text
Sacrifice a creature: Untap this creature. Activate only during your upkeep.
```

#### C52 — Klaw, Master of Sound (weak)

Combat damage exiles opposing cards and grants protection, but it lacks sacrifice, death, ETB, or graveyard-recursion value.

Caveat: Requires connecting in combat and an exile-casting package.

Evidence errors: none

Source C52:
```text
Whenever Klaw deals combat damage to a player
```

#### C53 — Evolved Spinoderm (support)

A self-sacrificing four-mana creature supplies a predictable death and can be replayed by Meren, with temporary hexproof or trample as useful secondary value.

Caveat: It takes four upkeeps to sacrifice itself and offers no ETB payoff.

Evidence errors: none

Source C53:
```text
At the beginning of your upkeep, remove an oil counter from this creature.
```

#### C54 — Phyrexian Altar (core)

A free sacrifice outlet produces colored mana, enabling Meren recursions and multiplying death-trigger value without requiring a tap.

Caveat: Mana production is one mana per creature and needs creatures to fuel it.

Evidence errors: none

Source C54:
```text
Sacrifice a creature: Add one mana of any color.
```

#### C55 — Cankerbloom (support)

A cheap recursive creature sacrifices for removal or proliferate, with proliferate able to increase Meren's experience counters and other counters.

Caveat: Each activation costs {1} and proliferate cannot create a counter where none exists.

Evidence errors: none

Source C55:
```text
Destroy target artifact.
• Destroy target enchantment.
• Proliferate.
```

#### C56 — Doubling Season (conditional)

Doubles token and counter production, improving sacrifice fodder and experience growth, but it has no direct engine ability and costs five mana.

Caveat: Needs token or counter-producing support to justify its cost.

Evidence errors: invalid_quote:C56

Source C56:
```text
If an effect would put one or more counters on a permanent you control, it puts twice that many counters
```

#### C57 — Shriekmaw (core)

Evoke supplies cheap ETB creature removal and immediate sacrifice, producing experience; Meren can repeatedly return it for removal loops.

Caveat: Only destroys nonartifact, nonblack creatures and evoke sacrifices it on entry.

Evidence errors: none

Source C57:
```text
When this creature enters, destroy target nonartifact, nonblack creature.
```

#### C58 — Paramecia Coloniex (support)

Mills on entry and, on death, places a chosen creature atop the library, setting up Meren's next recursion target and rewarding sacrifice.

Caveat: The death ability exiles this card and puts the target on top rather than directly returning it.

Evidence errors: none

Source C58:
```text
When this creature dies, you may exile it. When you do, put target creature card from your graveyard on top of your library.
```

#### C59 — Grafdigger's Cage (weak)

This directly prevents creature cards from entering the battlefield, shutting off Meren and most proposed recursion while offering only hate value.

Caveat: Use only in a dedicated anti-graveyard strategy.

Evidence errors: none

Source C59:
```text
Creature cards in graveyards and libraries can't enter the battlefield.
```

#### C60 — Ravenous Chupacabra (support)

A recursive ETB creature that destroys an opposing creature converts Meren's end-step returns into repeatable removal and board control.

Caveat: Four mana and {B}{B}; its destruction effect targets only an opponent's creature.

Evidence errors: none

Source C60:
```text
When this creature enters, destroy target creature an opponent controls.
```

#### C61 — Undercity Dire Rat (support)

Its death creates Treasure, turning sacrifice into mana while triggering Meren experience; recursion can repeatedly rebuild the resource.

Caveat: Treasure requires a separate tap-and-sacrifice activation to produce mana.

Evidence errors: none

Source C61:
```text
When this creature dies, create a Treasure token.
```

#### C62 — Zulaport Cutthroat (core)

A low-cost death payoff drains every opponent and gains life, converting repeated Meren sacrifices into scalable board-control payoff and a win condition.

Caveat: Its one toughness makes it vulnerable and it requires the creature to remain on the battlefield.

Evidence errors: none

Source C62:
```text
Whenever this creature or another creature you control dies, each opponent loses 1 life and you gain 1 life.
```

#### C63 — Evolution Sage (support)

Landfall proliferates experience counters and any other counters, while recurring land-sacrifice and ramp creatures can provide repeated land entries.

Caveat: Needs repeated land plays and proliferate only adds existing counter types.

Evidence errors: none

Source C63:
```text
Landfall — Whenever a land you control enters, proliferate.
```

## Saheeli — review

58.26 seconds; estimated $0.01400745.

Grounded rows: 59/64; complete validation: False.

### Actual rankings

1. **Gonti's Aether Heart** (C00, core; ranking valid: True)
   Produces substantial energy from every artifact entry and supplies an extra turn; Saheeli copies can double-trigger its entry ability before combat.
   Caveat: Six mana and eight-energy activation require a developed artifact board.
2. **Izzet Generatorium** (C60, core; ranking valid: False)
   Adds an extra energy whenever Saheeli, artifacts, or energy engines produce energy and later converts substantial energy expenditure into card draw.
   Caveat: Its draw ability requires four energy paid or lost that turn and tapping it.
3. **Aetherworks Marvel** (C37, core; ranking valid: True)
   Generates energy when permanents die and converts six energy into a free top-six spell, while remaining an artifact copy target.
   Caveat: Needs deaths and six energy; its ability taps and does not guarantee a hit.
4. **Decoction Module** (C05, core; ranking valid: True)
   Generates energy from every creature entry and can recycle your creatures for repeated entry triggers, including Saheeli copies before end step.
   Caveat: The bounce activation costs four mana and taps the Module.
5. **Whirler Virtuoso** (C08, core; ranking valid: True)
   Provides three energy on entry and converts energy into evasive artifact attackers; Saheeli can copy it for another entry burst.
   Caveat: Each Thopter costs three energy, competing with Saheeli's activation.
6. **Sai, Master Thopterist** (C11, core; ranking valid: True)
   Creates artifact Thopters from artifact casts, increasing board presence and sacrifice resources while Saheeli independently gains energy from those casts.
   Caveat: Its draw ability requires sacrificing two artifacts and four total mana.
7. **Forensic Gadgeteer** (C20, core; ranking valid: True)
   Investigates on every artifact cast for artifact card flow, while reducing artifact activation costs for energy engines and sacrifice outlets.
   Caveat: The reduction cannot lower mana portions below one.
8. **Panharmonicon** (C22, core; ranking valid: True)
   Doubles Saheeli-copy entry triggers and artifact/creature ETBs, greatly increasing energy, token, draw, and removal value from copied permanents.
   Caveat: Only doubles triggered abilities caused by artifact or creature entry.
9. **Fabrication Module** (C23, core; ranking valid: False)
   Converts every energy gain into creature growth and has its own energy production; Saheeli, Heart, and Generatorium can rapidly grow the board.
   Caveat: Requires creatures worth growing and four mana to activate its production.
10. **Mirage Mockery** (C24, core; ranking valid: True)
   Makes copies of artifact creatures or nonartifact creatures, and entwine supplies two bodies for combat and ETB/death value.
   Caveat: Entwine costs an additional three mana and copies lack Saheeli's temporary modifications.
11. **Jhoira, Weatherlight Captain** (C27, core; ranking valid: True)
   Draws from every historic spell, especially the deck's artifacts, while also being an Artificer spell that supplies Saheeli energy when cast.
   Caveat: Four-mana creature is vulnerable and must remain on the battlefield to draw.
12. **Academy Manufactor** (C31, support; ranking valid: True)
   Turns Clues from Gadgeteer into Clue, Food, and Treasure, multiplying artifacts, draw, life, and mana while supporting artifact-count payoffs.
   Caveat: Needs a Clue, Food, or Treasure producer to function.
13. **Enthusiastic Mechanaut** (C48, core; ranking valid: True)
   Cheap Artificer artifact that reduces artifact spell costs, increasing Saheeli energy generation, artifact density, and ability to deploy copy targets.
   Caveat: Reduction applies only to artifact spells and the 2/2 is fragile.
14. **Reckless Fireweaver** (C57, core; ranking valid: True)
   Deals damage whenever an artifact enters, including Saheeli copies, Thopters, Clues, and other token artifacts, converting deployment into reach.
   Caveat: Its one-damage trigger is incremental and it is vulnerable as a 1/3.
15. **Shuri, Wakandan Inventor** (C55, core; ranking valid: True)
   Cheap Artificer artifact-cost reducer also turns one artifact into a copy of another, enabling repeatable utility copying and Saheeli's artifact density.
   Caveat: Copy activation is sorcery-speed and requires two artifacts plus one mana.

### Every assessment (including unranked/failed)

#### C00 — Gonti's Aether Heart (core)

Produces substantial energy from every artifact entry and supplies an extra turn; Saheeli copies can double-trigger its entry ability before combat.

Caveat: Six mana and eight-energy activation require a developed artifact board.

Evidence errors: none

Source C00:
```text
Whenever Gonti's Aether Heart or another artifact you control enters, you get {E}{E}
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C01 — Aethertorch Renegade (support)

Enters with four energy and provides creature removal or reach; Saheeli can copy it for another energy burst and temporary utility.

Caveat: Removal is slow because it requires tapping and energy.

Evidence errors: none

Source C01:
```text
When this creature enters, you get {E}{E}{E}{E}
```

Source C01:
```text
{T}, Pay {E}{E}: This creature deals 1 damage to target creature.
```

#### C02 — Ordinary Bear (weak)

A 4/5 body can attack and be copied, but it supplies no artifact, Artificer, energy, entry, or combat-value engine.

Caveat: Only reasonable in a creature-heavy combat direction.

Evidence errors: none

Source C02:
```text
Creature — Bear
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C03 — Fantastic Bounce (support)

Bounces an opposing permanent or your own entry-value creature, and draws a card; targeting a tapped creature reduces its cost.

Caveat: Sorcery-speed four-mana interaction is not an energy engine.

Evidence errors: invalid_quote:C03

Source C03:
```text
Return target nonland permanent to its owner's hand. Draw a card.
```

Source C03:
```text
This spell costs {2} less to cast if it targets a tapped creature.
```

#### C04 — Second Harvest (conditional)

Copies every token, potentially multiplying Thopters, Servos, and Saheeli-created bodies for combat and sacrifice value.

Caveat: Requires a substantial token board and four green mana.

Evidence errors: none

Source C04:
```text
For each token you control, create a token that's a copy of that permanent.
```

Source D0:
```text
create a token that's a copy of target permanent you control
```

#### C05 — Decoction Module (core)

Generates energy from every creature entry and can recycle your creatures for repeated entry triggers, including Saheeli copies before end step.

Caveat: The bounce activation costs four mana and taps the Module.

Evidence errors: none

Source C05:
```text
Whenever a creature you control enters, you get {E}
```

Source C05:
```text
{4}, {T}: Return target creature you control to its owner's hand.
```

#### C06 — Brudiclad, Telchor Engineer (conditional)

Creates a token every combat and converts tokens into copies, giving Saheeli many artifact bodies and strong combat scaling.

Caveat: Six mana and a token package are needed; its combat trigger competes with Saheeli's timing.

Evidence errors: none

Source C06:
```text
At the beginning of combat on your turn, create a 2/1 blue Phyrexian Myr artifact creature token.
```

Source C06:
```text
each other token you control becomes a copy of that token.
```

#### C07 — Plasma Caster (support)

Attacking with equipped creatures supplies two energy and gives blocking interaction, while the Equipment is an artifact spell for Saheeli.

Caveat: Coin flip makes the removal unreliable and equip costs two.

Evidence errors: none

Source C07:
```text
Whenever equipped creature attacks, you get {E}{E}
```

Source C07:
```text
Flip a coin. If you win the flip, exile the chosen creature.
```

#### C08 — Whirler Virtuoso (core)

Provides three energy on entry and converts energy into evasive artifact attackers; Saheeli can copy it for another entry burst.

Caveat: Each Thopter costs three energy, competing with Saheeli's activation.

Evidence errors: none

Source C08:
```text
When this creature enters, you get {E}{E}{E}
```

Source C08:
```text
Pay {E}{E}{E}: Create a 1/1 colorless Thopter artifact creature token with flying.
```

#### C09 — Wheel of Potential (support)

Adds three energy and can refresh hands; spending energy can enable a large redraw and temporary access to exiled cards.

Caveat: The strongest mode requires paying seven energy and benefits all players.

Evidence errors: none

Source C09:
```text
You get {E}{E}{E} (three energy counters)
```

Source C09:
```text
If seven or more {E} was paid this way, you may play cards you own exiled this way
```

#### C10 — Mirrormere Guardian (weak)

Its death only tempts the Ring, offering no artifact, energy, copy, or combat synergy for Saheeli.

Caveat: Requires a separate Ring-tempt strategy.

Evidence errors: none

Source C10:
```text
When this creature dies, the Ring tempts you.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C11 — Sai, Master Thopterist (core)

Creates artifact Thopters from artifact casts, increasing board presence and sacrifice resources while Saheeli independently gains energy from those casts.

Caveat: Its draw ability requires sacrificing two artifacts and four total mana.

Evidence errors: none

Source C11:
```text
Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.
```

Source C11:
```text
Sacrifice two artifacts: Draw a card.
```

#### C12 — Arcbound Overseer (weak)

An eight-mana modular creature is expensive and lacks energy or entry value; its counters do not naturally support Saheeli's copy plan.

Caveat: Needs a dedicated modular and artifact-counter package.

Evidence errors: none

Source C12:
```text
Modular 6 (This creature enters with six +1/+1 counters on it.
```

Source C12:
```text
At the beginning of your upkeep, put a +1/+1 counter
```

#### C13 — Cryptic Coat (conditional)

Provides an unblockable equipped attacker and cloaks a card, offering combat pressure and an artifact target for copying.

Caveat: Cloaked-card value and face-up access depend on the top card being a creature.

Evidence errors: none

Source C13:
```text
Equipped creature gets +1/+0 and can't be blocked.
```

Source C13:
```text
Turn it face up any time for its mana cost if it's a creature card.
```

#### C14 — Carapace Forger (support)

A cheap Artificer advances Saheeli's energy when cast and becomes a 4/4 with three artifacts, contributing a useful combat body.

Caveat: Its payoff requires controlling at least three artifacts.

Evidence errors: none

Source C14:
```text
Metalcraft — This creature gets +2/+2 as long as you control three or more artifacts.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C15 — Princess Yue (weak)

Provides scry and self-reanimation as a land, but is neither artifact nor Artificer and has no copy, energy, or combat payoff.

Caveat: Its unusual death transformation may have value in a landfall shell.

Evidence errors: none

Source C15:
```text
When Princess Yue dies, if she was a nonland creature, return this card to the battlefield tapped
```

Source C15:
```text
{T}: Scry 2.
```

#### C16 — Lembas (support)

Cheap artifact entry draw improves consistency and supplies an artifact permanent for Saheeli's copy targets; sacrifice gains life and recycles it.

Caveat: Its graveyard replacement prevents normal death-recursion lines.

Evidence errors: none

Source C16:
```text
When this artifact enters, scry 1, then draw a card.
```

Source C16:
```text
When this artifact is put into a graveyard from the battlefield, its owner shuffles it into their library.
```

#### C17 — Efficient Construction (support)

Turns every artifact cast into an evasive artifact token, multiplying Saheeli's combat bodies and artifact count.

Caveat: Four-mana enchantment has no direct energy production.

Evidence errors: none

Source C17:
```text
Whenever you cast an artifact spell, create a 1/1 colorless Thopter artifact creature token with flying.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C18 — Giant-Man, Gargantuan Genius (conditional)

Creates green mana from each large creature, and Saheeli's 5/5 copies can increase that count for later turns.

Caveat: Requires multiple creatures with power four or greater and is not an artifact.

Evidence errors: none

Source C18:
```text
add {G} for each creature you control with power 4 or greater.
```

Source D0:
```text
it's a 5/5 artifact creature in addition to its other types
```

#### C19 — Ember Island Production (support)

Creates a 4/4 copy of your creature, or steals an opposing creature copy, adding immediate combat bodies independent of energy.

Caveat: Five-mana sorcery cannot copy noncreatures or provide repeatable value.

Evidence errors: none

Source C19:
```text
Create a token that's a copy of target creature you control
```

Source C19:
```text
Create a token that's a copy of target creature an opponent controls
```

#### C20 — Forensic Gadgeteer (core)

Investigates on every artifact cast for artifact card flow, while reducing artifact activation costs for energy engines and sacrifice outlets.

Caveat: The reduction cannot lower mana portions below one.

Evidence errors: none

Source C20:
```text
Whenever you cast an artifact spell, investigate.
```

Source C20:
```text
Activated abilities of artifacts you control cost {1} less to activate.
```

#### C21 — Carnivorous Cultivator // Enroot (weak)

The creature is an off-plan land-recovery body and the sorcery only places a land in the graveyard; neither advances artifacts, energy, or copies.

Caveat: Needs a graveyard-land or landfall package.

Evidence errors: none

Source C21:
```text
Search your library for a land card, put it into your graveyard
```

Source C21:
```text
return target land card from your graveyard to your hand.
```

#### C22 — Panharmonicon (core)

Doubles Saheeli-copy entry triggers and artifact/creature ETBs, greatly increasing energy, token, draw, and removal value from copied permanents.

Caveat: Only doubles triggered abilities caused by artifact or creature entry.

Evidence errors: none

Source C22:
```text
that ability triggers an additional time.
```

Source D0:
```text
create a token that's a copy of target permanent you control
```

#### C23 — Fabrication Module (core)

Converts every energy gain into creature growth and has its own energy production; Saheeli, Heart, and Generatorium can rapidly grow the board.

Caveat: Requires creatures worth growing and four mana to activate its production.

Evidence errors: invalid_quote:C23

Source C23:
```text
Whenever you get one or more {E}, put a +1/+1 counter on target creature you control.
```

Source C23:
```text
{4}, {T}: You get {E}.
```

#### C24 — Mirage Mockery (core)

Makes copies of artifact creatures or nonartifact creatures, and entwine supplies two bodies for combat and ETB/death value.

Caveat: Entwine costs an additional three mana and copies lack Saheeli's temporary modifications.

Evidence errors: none

Source C24:
```text
Create a token that's a copy of target artifact creature you control.
```

Source C24:
```text
Entwine {2}{U}
```

#### C25 — W'Kabi, Shield of the Nation (support)

Rewards attacking with Saheeli by creating a trampling Rhino when a qualifying large artifact is controlled, adding combat pressure.

Caveat: Requires attacking with the commander and an artifact with mana value at least four.

Evidence errors: none

Source C25:
```text
Whenever you attack with your commander
```

Source C25:
```text
create a 4/4 green Rhino creature token with trample.
```

#### C26 — Wurmcoil Engine (support)

Excellent Saheeli copy target: its death creates two artifact bodies, and its lifelink/deathtouch makes the temporary 5/5 copy valuable in combat.

Caveat: Six mana and no energy production make it a top-end target.

Evidence errors: none

Source C26:
```text
When this creature dies, create a 3/3 colorless Phyrexian Wurm artifact creature token
```

Source D0:
```text
Sacrifice it at the beginning of the next end step.
```

#### C27 — Jhoira, Weatherlight Captain (core)

Draws from every historic spell, especially the deck's artifacts, while also being an Artificer spell that supplies Saheeli energy when cast.

Caveat: Four-mana creature is vulnerable and must remain on the battlefield to draw.

Evidence errors: none

Source C27:
```text
Whenever you cast a historic spell, draw a card.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C28 — Solemn Simulacrum (support)

Artifact ramp searches a basic on entry and draws on death; Saheeli can copy it for additional land acceleration and later death value.

Caveat: Four mana for a 2/2 is slow without blink, sacrifice, or copy support.

Evidence errors: none

Source C28:
```text
When this creature enters, you may search your library for a basic land card
```

Source C28:
```text
When this creature dies, you may draw a card.
```

#### C29 — Doubling Season (conditional)

Doubles Saheeli's temporary copy and token engines and doubles +1/+1 counters from Fabrication Module.

Caveat: Five mana and nonartifact status mean it needs a token/counter-heavy build.

Evidence errors: none

Source C29:
```text
it creates twice that many of those tokens instead.
```

Source C29:
```text
it puts twice that many of those counters on that permanent instead.
```

#### C30 — Hawkeye, Avenging Archer (weak)

Offers a tap damage ability and conditional card draw after its own damage, but lacks artifact, energy, copy, or broad combat synergy.

Caveat: Needs a dedicated ping or deathtouch-damage package.

Evidence errors: none

Source C30:
```text
Whenever a creature an opponent controls dies, if Hawkeye dealt damage to it this turn, draw a card.
```

Source C30:
```text
{T}: Hawkeye deals 1 damage to any target.
```

#### C31 — Academy Manufactor (support)

Turns Clues from Gadgeteer into Clue, Food, and Treasure, multiplying artifacts, draw, life, and mana while supporting artifact-count payoffs.

Caveat: Needs a Clue, Food, or Treasure producer to function.

Evidence errors: none

Source C31:
```text
If you would create a Clue, Food, or Treasure token, instead create one of each.
```

Source C20:
```text
Whenever you cast an artifact spell, investigate.
```

#### C32 — Triplicate Titan (conditional)

A powerful Saheeli copy target whose death leaves three artifact bodies, with evasive combat keywords on the original.

Caveat: Nine mana is a major prerequisite and it produces value only on death.

Evidence errors: none

Source C32:
```text
When this creature dies, create a 3/3 colorless Golem artifact creature token
```

Source C32:
```text
Flying, vigilance, trample
```

#### C33 — Pet Avengers (weak)

Creates one nonartifact Hero token and a counter through a costly once-only activation, without energy or artifact interaction.

Caveat: Needs a creature-token combat or power-up strategy.

Evidence errors: none

Source C33:
```text
create a 3/2 white Hero creature token with vigilance.
```

Source C33:
```text
Activate each power-up ability only once.
```

#### C34 — Hand of Emrakul (weak)

A nine-mana Eldrazi has no artifact, energy, copy, or entry value; its sacrifice alternative needs an absent Spawn package.

Caveat: Requires four Eldrazi Spawn or substantial ramp.

Evidence errors: none

Source C34:
```text
You may sacrifice four Eldrazi Spawn rather than pay this spell's mana cost.
```

Source C34:
```text
Annihilator 1
```

#### C35 — Bristly Bill, Spine Sower (conditional)

Builds +1/+1 counters through landfall and doubles them, complementing Fabrication Module and proliferate-style counter plans.

Caveat: Needs frequent land entries and substantial green mana for doubling.

Evidence errors: none

Source C35:
```text
Landfall — Whenever a land you control enters, put a +1/+1 counter on target creature.
```

Source C35:
```text
Double the number of +1/+1 counters on each creature you control.
```

#### C36 — Cogwork Tracker (weak)

An artifact body can be cast for Saheeli energy and attack, but draft-only text and forced attacks make it poor Commander utility.

Caveat: Its noted-player ability is not meaningful in ordinary Commander play.

Evidence errors: none

Source C36:
```text
Reveal this card as you draft it and note the player who passed it to you.
```

Source C36:
```text
This creature attacks each combat if able.
```

#### C37 — Aetherworks Marvel (core)

Generates energy when permanents die and converts six energy into a free top-six spell, while remaining an artifact copy target.

Caveat: Needs deaths and six energy; its ability taps and does not guarantee a hit.

Evidence errors: none

Source C37:
```text
Whenever a permanent you control is put into a graveyard, you get {E}
```

Source C37:
```text
Look at the top six cards of your library. You may cast a spell
```

#### C38 — Inventor's Axe (support)

One-mana artifact gives two energy and immediate +2/+0, with energy equip enabling repeated combat use and Saheeli triggering on cast.

Caveat: Equip consumes the same energy needed for Saheeli's copy activation.

Evidence errors: none

Source C38:
```text
When this Equipment enters, you get {E}{E}
```

Source C38:
```text
Equip—Pay {E}{E}.
```

#### C39 — Janjeet Sentry (support)

Provides two energy and can tap or untap artifacts and creatures, enabling combat manipulation or repeated tap abilities.

Caveat: Requires tapping the creature and two energy per activation.

Evidence errors: none

Source C39:
```text
When this creature enters, you get {E}{E}
```

Source C39:
```text
You may tap or untap target artifact or creature.
```

#### C40 — Retrofitter Foundry (conditional)

Produces artifact tokens and upgrades them from Servo to Thopter to Construct, supplying Saheeli artifacts, attackers, and sacrifice material.

Caveat: Each conversion requires tapping and appropriate disposable tokens.

Evidence errors: none

Source C40:
```text
Create a 1/1 colorless Servo artifact creature token.
```

Source C40:
```text
Sacrifice a Thopter: Create a 4/4 colorless Construct artifact creature token.
```

#### C41 — Jaws, Relentless Predator (weak)

Creates Blood through combat and pings opponents when noncreature artifacts are sacrificed, but is a costly nonartifact creature outside the energy plan.

Caveat: Needs a high-power attacker and many noncreature artifact sacrifices.

Evidence errors: none

Source C41:
```text
Whenever Jaws deals combat damage to a player, create that many Blood tokens.
```

Source C41:
```text
Whenever a noncreature artifact is sacrificed or destroyed
```

#### C42 — Faces of the Past (weak)

Its death-triggered tapping or untapping is unpredictable and tribal-dependent, with no artifact, energy, copy, or direct combat payoff.

Caveat: Needs a concentrated shared-creature-type board and death outlets.

Evidence errors: none

Source C42:
```text
Whenever a creature dies, tap all untapped creatures that share a creature type with it
```

Source C42:
```text
or untap all tapped creatures that share a creature type with it.
```

#### C43 — Evolution Sage (support)

Landfall proliferates energy counters, +1/+1 counters, and other existing counters, extending Saheeli's stored energy and Fabrication growth.

Caveat: Requires landfall triggers and counters already present; proliferate does not create energy from nothing.

Evidence errors: invalid_quote:R02

Source C43:
```text
Landfall — Whenever a land you control enters, proliferate.
```

Source R02:
```text
give each another counter of each kind already there.
```

#### C44 — Mirran Spy (support)

Untaps a creature whenever an artifact is cast, enabling repeated tap abilities and attack preparation while also being an evasive body.

Caveat: It does not untap artifacts and provides no energy itself.

Evidence errors: none

Source C44:
```text
Whenever you cast an artifact spell, you may untap target creature.
```

Source C44:
```text
Flying
Whenever you cast an artifact spell
```

#### C45 — Hangarback Walker (conditional)

Scales as an artifact creature and leaves flying artifact Thopters on death; counters from Fabrication Module make both halves stronger.

Caveat: Requires mana to cast and grow, plus a sacrifice or death-value plan.

Evidence errors: none

Source C45:
```text
When this creature dies, create a 1/1 colorless Thopter artifact creature token with flying for each +1/+1 counter
```

Source C45:
```text
{1}, {T}: Put a +1/+1 counter on this creature.
```

#### C46 — Sundial of the Infinite (conditional)

Can end your turn after Saheeli's delayed sacrifice is put on the stack, potentially preserving a temporary copy for later turns.

Caveat: Requires exact stack timing and sacrifices ending the turn's remaining actions.

Evidence errors: none

Source C46:
```text
End the turn.
```

Source D0:
```text
Sacrifice it at the beginning of the next end step.
```

#### C47 — Drown in Shapelessness (weak)

Cheap creature bounce is useful interaction, but it neither advances artifacts, energy, copying, nor card advantage.

Caveat: Could be playable only if unusually high creature-bounce density is desired.

Evidence errors: none

Source C47:
```text
Return target creature to its owner's hand.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C48 — Enthusiastic Mechanaut (core)

Cheap Artificer artifact that reduces artifact spell costs, increasing Saheeli energy generation, artifact density, and ability to deploy copy targets.

Caveat: Reduction applies only to artifact spells and the 2/2 is fragile.

Evidence errors: none

Source C48:
```text
Artifact spells you cast cost {1} less to cast.
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C49 — Thought Monitor (support)

Affinity makes this artifact creature affordable in a developed board and its entry draws two cards, making it an attractive Saheeli copy target.

Caveat: Seven-mana base cost is poor before artifact density is established.

Evidence errors: none

Source C49:
```text
This spell costs {1} less to cast for each artifact you control.
```

Source C49:
```text
When this creature enters, draw two cards.
```

#### C50 — Black Widow, Natasha Romanoff (weak)

Has no rules text and therefore supplies no artifact, energy, copy, draw, or combat interaction beyond its basic body.

Caveat: Only relevant if its text is supplied elsewhere.

Evidence errors: invalid_quote:C50

Source C50:
```text
oracle_text": ""
```

Source D0:
```text
Whenever you cast an Artificer or artifact spell, you get {E}
```

#### C51 — Oviya Pashiri, Sage Lifecrafter (conditional)

Produces Servo or scalable Construct artifact tokens, supplying artifact count and combat bodies for Saheeli and sacrifice engines.

Caveat: Token production is mana- and tap-intensive and needs Oviya to survive.

Evidence errors: none

Source C51:
```text
Create a 1/1 colorless Servo artifact creature token.
```

Source C51:
```text
Create an X/X colorless Construct artifact creature token
```

#### C52 — Bloodthorn Taunter (weak)

Provides haste to itself and one large creature, but offers no artifact, energy, copy, entry, or meaningful board-wide combat support.

Caveat: Needs multiple power-five creatures to justify the tap ability.

Evidence errors: none

Source C52:
```text
Target creature with power 5 or greater gains haste until end of turn.
```

Source C52:
```text
Haste
{T}:
```

#### C53 — Daretti, Scrap Savant (support)

Loots unwanted cards and exchanges an artifact for a graveyard artifact, enabling death triggers and recurring high-value copy targets.

Caveat: The recursion ability requires an artifact in the graveyard and sacrifices another artifact.

Evidence errors: none

Source C53:
```text
Sacrifice an artifact. If you do, return target artifact card from your graveyard to the battlefield.
```

Source C53:
```text
+2: Discard up to two cards, then draw that many cards.
```

#### C54 — Myr Battlesphere (conditional)

Entry creates four artifact tokens and attack converts Myr into extra damage and power, making it a premium Saheeli copy target.

Caveat: Seven mana and a sizable Myr board are required for maximum combat value.

Evidence errors: none

Source C54:
```text
When this creature enters, create four 1/1 colorless Myr artifact creature tokens.
```

Source C54:
```text
Whenever this creature attacks, you may tap X untapped Myr you control.
```

#### C55 — Shuri, Wakandan Inventor (core)

Cheap Artificer artifact-cost reducer also turns one artifact into a copy of another, enabling repeatable utility copying and Saheeli's artifact density.

Caveat: Copy activation is sorcery-speed and requires two artifacts plus one mana.

Evidence errors: none

Source C55:
```text
Artifact spells you cast cost {1} less to cast.
```

Source C55:
```text
Target artifact you control becomes a copy of a second target artifact you control
```

#### C56 — Meteor Golem (conditional)

A Saheeli copy can enter as a 5/5 artifact version of Meteor Golem and trigger destruction of an opposing nonland permanent.

Caveat: Seven mana is expensive and the copy's delayed sacrifice limits repeat use.

Evidence errors: none

Source C56:
```text
When this creature enters, destroy target nonland permanent an opponent controls.
```

Source D0:
```text
create a token that's a copy of target permanent you control
```

#### C57 — Reckless Fireweaver (core)

Deals damage whenever an artifact enters, including Saheeli copies, Thopters, Clues, and other token artifacts, converting deployment into reach.

Caveat: Its one-damage trigger is incremental and it is vulnerable as a 1/3.

Evidence errors: none

Source C57:
```text
Whenever an artifact you control enters, this creature deals 1 damage to each opponent.
```

Source D0:
```text
it's a 5/5 artifact creature in addition to its other types
```

#### C58 — Kiln Walker (support)

Cheap artifact attacker becomes a 3/3 on attack, benefiting from Saheeli's haste and providing a simple combat payoff and copy target.

Caveat: It has no energy or entry value and only improves during attacks.

Evidence errors: none

Source C58:
```text
Whenever this creature attacks, it gets +3/+0 until end of turn.
```

Source C58:
```text
Artifact Creature — Phyrexian Construct
```

#### C59 — Dowsing Dagger // Lost Vale (support)

Creates an attackable combat target for an opponent and can transform after combat damage into a three-mana land, improving ramp and combat pressure.

Caveat: Needs an equipped creature to connect and gives the opponent two Plant blockers.

Evidence errors: none

Source C59:
```text
Whenever equipped creature deals combat damage to a player, you may transform this Equipment.
```

Source C59:
```text
{T}: Add three mana of any one color.
```

#### C60 — Izzet Generatorium (core)

Adds an extra energy whenever Saheeli, artifacts, or energy engines produce energy and later converts substantial energy expenditure into card draw.

Caveat: Its draw ability requires four energy paid or lost that turn and tapping it.

Evidence errors: invalid_quote:C60

Source C60:
```text
If you would get one or more {E}, you get that many plus one {E} instead.
```

Source C60:
```text
Draw a card. Activate only if you've paid or lost four or more {E} this turn.
```

#### C61 — It of the Horrid Swarm (weak)

An eight-mana nonartifact creature creates two nonartifact Insects but supplies no energy, artifact, copy, or relevant entry payoff.

Caveat: Requires a dedicated emerge or Eldrazi-Spawn package.

Evidence errors: none

Source C61:
```text
When you cast this spell, create two 1/1 green Insect creature tokens.
```

Source C61:
```text
Emerge {6}{G}
```

#### C62 — Zimone's Hypothesis (conditional)

Can grow a creature then return creatures of a chosen parity, offering mass interaction and possible self-bounce of valuable entry creatures.

Caveat: Five mana and parity selection can also return your own board or miss key targets.

Evidence errors: none

Source C62:
```text
You may put a +1/+1 counter on a creature.
```

Source C62:
```text
Return each creature with power of the chosen quality to its owner's hand.
```

#### C63 — Torpor Orb (weak)

Suppresses all creature-entry triggers, directly disabling Saheeli copy targets, energy creatures, Thopter engines, and many candidate payoffs.

Caveat: Only suitable as a metagame hate piece despite severe self-conflict.

Evidence errors: none

Source C63:
```text
Creatures entering don't cause abilities to trigger.
```

Source D0:
```text
At the beginning of combat on your turn, you may pay {E}{E}{E}
```
