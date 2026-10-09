# Actual Luna/Terra plans and ranked suggestions

Eight authorized calls completed; no retries. These are model outputs, not certified rules.
Both models reviewed the same 64-card pool per commander, including forced diagnostics.
Read [README.md](README.md) for discovery attribution and supported factual findings.

**Formatting caveat:** Terra returned `Cxx — Card name` instead of bare recommendation IDs.
The frozen schema accepted arbitrary strings; the strict scorer correctly rejected all
30 decorated ranked identifiers. Below, each intended card is shown only after its prefix
and name/front alias match the supplied source. This human-readable view does not change
the raw outputs or original validation. Literal quote failures are flagged separately.

## Meren / gpt-5.6-luna

### Planning intentions

- Build a sacrifice engine that turns expendable creatures into experience counters, cards, mana, removal, or board control.
- Prioritize creatures with useful enter-the-battlefield or death triggers that become repeatable through Meren's end-step recursion.
- Support reliable sacrifice outlets, recursive fodder, graveyard access, and protection so Meren retains value after removal.
- Exploit both sides of Meren's threshold: recur low-mana-value utility creatures directly, while recovering larger creatures to hand for later casting.
- Include interaction attached to creatures where possible, while recognizing that Meren only returns a creature card and does not automatically reuse noncreature spells.

### Actual executable searches

1. **Free or repeatable sacrifice outlets that convert creatures into cards, mana, life, or other resources.**
   - Filters: `{"oracle_text_all": ["sacrifice a creature"]}`
   - 235 matches; 8 sampled.
2. **Creature-based card advantage from entering or dying, suitable for repeated Meren recursion.**
   - Filters: `{"oracle_text_any": ["When this creature enters", "Whenever this creature dies", "When this creature dies"], "type_line_any": ["Creature"]}`
   - 1462 matches; 8 sampled.
3. **Creature removal or interaction attached to entry or death triggers.**
   - Filters: `{"oracle_text_any": ["When this creature enters", "Whenever this creature dies", "When this creature leaves the battlefield"], "type_line_any": ["Creature"]}`
   - 1176 matches; 8 sampled.
4. **Small creatures with self-recursion or graveyard return that provide repeatable sacrifice fodder and experience counters.**
   - Filters: `{"oracle_text_any": ["return this card from your graveyard to the battlefield", "return it to the battlefield", "return this card to the battlefield"], "type_line_any": ["Creature"], "mana_value_max": 2.0}`
   - 47 matches; 8 sampled.
5. **Creature-based mana production that can be sacrificed and replayed for ramp or resource conversion.**
   - Filters: `{"oracle_text_any": ["add one mana", "add {", "search your library for a basic land"], "type_line_any": ["Creature"], "mana_value_max": 3.0}`
   - 294 matches; 8 sampled.
6. **Ways to protect Meren or a key creature while preserving a sacrifice-and-recursion board.**
   - Filters: `{"oracle_text_any": ["hexproof", "indestructible", "return target creature you control to its owner's hand"], "type_line_any": ["Creature"], "mana_value_max": 4.0}`
   - 101 matches; 8 sampled.
7. **Creatures that reward repeated deaths or graveyard activity with broad scaling, counters, tokens, or life loss.**
   - Filters: `{"oracle_text_any": ["Whenever another creature dies", "Whenever a creature dies", "from your graveyard"], "type_line_any": ["Creature"]}`
   - 553 matches; 8 sampled.

**Nominated names:** Viscera Seer; Carrion Feeder; Ashnod's Altar; Phyrexian Altar; Yahenni, Undying Partisan; Spore Frog; Eternal Witness; Reclamation Sage; Ravenous Chupacabra; Plaguecrafter; Sakura-Tribe Elder; Solemn Simulacrum.

**Model-stated uncertainty:**
- Exact card selection should account for whether each trigger is an enter-the-battlefield trigger, death trigger, cast trigger, or leaves-the-battlefield trigger; Meren's recursion only returns the creature and does not retrigger cast-only abilities.
- A sacrifice outlet is not automatically a mana-positive or card-positive engine; the deck needs compatible fodder and payoff pieces, and sacrifice costs may require specific timing.
- Meren's end-step trigger targets a creature card and compares its mana value with experience counters; larger creatures returned to hand may need separate ramp or reanimation support.
- Creature-based interaction is especially attractive because it can be reused, but ETB triggers only function when the creature actually enters the battlefield, including after Meren returns it.

### Actual ranked suggestions

Quote/identity-grounded assessments: 61/64; strict accepted ranked items: 15/15.
These counts measure output grounding/conformance, not strategic or semantic accuracy.

1. **Viscera Seer** — core
   - A free sacrifice outlet scries after every death, building experience while filtering draws and enabling repeatable ETB/death loops.
   - Caveat: Scry 1 is selection, not card advantage; it needs creatures to sacrifice.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
2. **Stitcher's Supplier** — core
   - One-mana self-mill creature stocks the graveyard and becomes a cheap sacrifice/recursion target, with both entry and death milling.
   - Caveat: Milling is not selection and can put important cards in the graveyard unintentionally.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
3. **Yawgmoth, Thran Physician** — core
   - Free sacrifice plus card draw and creature removal directly fuels Meren's experience engine; proliferate can increase existing counters, including experience counters.
   - Caveat: Requires paying life and {B}{B} plus discarding for proliferate; proliferate cannot create a counter absent already one.
   - Own independent shortlist: no; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
4. **Ashnod's Altar** — core
   - Free sacrifice outlet converts every creature into two mana, enabling repeated death triggers, recast costs, and sacrifice-based value engines.
   - Caveat: Produces colorless mana only and requires creatures to sacrifice.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
5. **Phyrexian Altar** — core
   - Free colored-mana sacrifice outlet enables repeated death triggers, pays colored recursion costs, and supports sacrifice loops when other pieces provide returns.
   - Caveat: Requires creatures to sacrifice; no loop exists from this card alone.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist.
6. **Sakura-Tribe Elder** — core
   - Free sacrifice converts a creature into a basic land, building experience while fixing and ramping; Meren can later return the Elder for repeatable value.
   - Caveat: Only finds basic lands and puts them tapped.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
7. **Reclamation Sage** — core
   - A creature-based artifact/enchantment answer is reusable through Meren; its entry death can also build experience when sacrificed afterward.
   - Caveat: Only answers artifacts or enchantments, not creatures.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
8. **Satyr Wayfinder** — core
   - Fills the graveyard while finding a land, then becomes a cheap Meren target and sacrifice body for repeated selection and experience.
   - Caveat: Only four cards are milled and at most one land is found.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
9. **Plaguecrafter** — core
   - Entry forces each player to sacrifice or discard, providing interaction and a death trigger; Meren can repeatedly reuse this disruptive creature.
   - Caveat: Symmetrical and opponents choose what they sacrifice or discard.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist.
10. **Shriekmaw** — core
   - Evoke supplies cheap creature removal and sacrifices Shriekmaw immediately, while Meren can recur it for repeated ETB removal.
   - Caveat: Only destroys nonartifact, nonblack creatures; full cast costs five mana.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
11. **Morbid Opportunist** — core
   - Draws once each turn whenever creatures die, converting Meren's sacrifice engine into cards while remaining a cheap recur-able creature.
   - Caveat: Only one trigger each turn, even if many creatures die.
   - Own independent shortlist: no; channels: diagnostic.
12. **Grim Haruspex** — core
   - Draws for each nontoken creature death, making sacrifice and Meren recursion into sustained cards while its body remains recur-able.
   - Caveat: Does not trigger from token deaths and must be face-up to provide the ability.
   - Own independent shortlist: no; channels: diagnostic.
13. **Blood Artist** — core
   - Turns every creature death into life loss and life gain, providing a win condition and stabilizing life while Meren supplies repeatable deaths.
   - Caveat: Targets one player per trigger and does not draw cards or create mana.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
14. **Zulaport Cutthroat** — core
   - A cheap death payoff drains every opponent and gains life, giving sacrifice loops a win condition while Meren supplies recurring creatures.
   - Caveat: Only triggers from creatures you control, not all creatures dying.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
15. **Eternal Witness** — core
   - Returns any graveyard card to hand on entry, giving Meren access to noncreatures and enabling repeated utility through creature recursion.
   - Caveat: Returns to hand rather than battlefield and costs three mana to cast.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.

## Meren / gpt-5.6-terra

### Planning intentions

- Create reliable creature-death throughput to build experience counters while converting bodies into mana, cards, tokens, or disruption.
- Prioritize cheap creatures whose ETB, death, or sacrifice text remains useful when Meren returns them every end step.
- Include sacrifice outlets that let the deck control timing, protect creatures from exile-based answers, and turn recursion into repeatable value.
- Use self-mill, discard, and creature-based tutoring to stock the graveyard; retain value when Meren returns a card to hand before sufficient experience is built.
- Add graveyard interaction and removal on recurrable creature bodies, plus resilience against opposing graveyard disruption.
- Explore token production and creatures that recur themselves, since expendable material fuels both outlets and Meren's experience engine.

### Actual executable searches

1. **Free or low-friction repeatable sacrifice outlets, including ones that generate a concrete payoff while enabling precise death timing.**
   - Filters: `{"oracle_text_all": ["Sacrifice a creature"], "oracle_text_any": ["Activate only", "any time"], "mana_value_max": 4.0}`
   - 17 matches; 8 sampled.
2. **Creature bodies with explicit death triggers that provide cards, mana, tokens, life drain, or removal when repeatedly sacrificed and returned.**
   - Filters: `{"oracle_text_all": ["dies"], "oracle_text_any": ["draw", "create", "add {", "loses", "destroy target"], "type_line_any": ["Creature"], "mana_value_max": 5.0}`
   - 228 matches; 8 sampled.
3. **Low-cost ETB creatures that provide repeatable interaction or resource generation after Meren reanimates them.**
   - Filters: `{"oracle_text_all": ["When"], "oracle_text_any": ["enters", "enters the battlefield"], "type_line_any": ["Creature"], "mana_value_max": 4.0}`
   - 1162 matches; 8 sampled.
4. **Creature-based graveyard setup that mills, discards, or returns creature cards from the graveyard, increasing Meren's available end-step choices.**
   - Filters: `{"oracle_text_any": ["mill", "discard", "creature card from your graveyard"], "type_line_any": ["Creature"], "mana_value_max": 5.0}`
   - 552 matches; 8 sampled.
5. **Creatures that naturally return themselves from the graveyard, supplying recurring sacrifice material independent of Meren's end-step trigger.**
   - Filters: `{"oracle_text_all": ["from your graveyard"], "oracle_text_any": ["return", "put"], "type_line_any": ["Creature"], "mana_value_max": 5.0}`
   - 344 matches; 8 sampled.
6. **Creature-based answers that can be repeatedly deployed through Meren against artifacts, enchantments, creatures, or graveyards.**
   - Filters: `{"oracle_text_any": ["destroy target artifact", "destroy target enchantment", "exile target card from a graveyard", "destroy target creature"], "type_line_any": ["Creature"], "mana_value_max": 6.0}`
   - 132 matches; 8 sampled.
7. **Death-trigger multipliers or replacements that accelerate experience acquisition and amplify sacrifice payoffs.**
   - Filters: `{"oracle_text_any": ["dies triggers", "dies trigger", "If a creature dying causes"], "mana_value_max": 6.0}`
   - 2 matches; 2 sampled.
8. **Token-producing creatures and permanents that create disposable bodies, preferably in response to creature deaths or repeated creature entry.**
   - Filters: `{"oracle_text_all": ["create"], "oracle_text_any": ["Creature token", "creature token"], "mana_value_max": 6.0}`
   - 917 matches; 8 sampled.

**Nominated names:** Viscera Seer; Carrion Feeder; Yawgmoth, Thran Physician; Ashnod's Altar; Blood Artist; Zulaport Cutthroat; Sakura-Tribe Elder; Satyr Wayfinder; Stitcher's Supplier; Eternal Witness; Shriekmaw; Reclamation Sage.

**Model-stated uncertainty:**
- Meren's triggered ability targets at the beginning of the end step, so a creature sacrificed after that trigger is put on the stack normally will not be a legal target for that instance; the deck benefits from outlets usable before the end step.
- The commander only returns another creature's death into an experience counter; Meren dying herself does not add experience.
- Meren returns only creature cards, so noncreature engines and outlets may be strong but cannot be directly recurred by her.
- A card returned to hand at low experience must be recast; the desired balance between cheap replayable creatures and larger eventual reanimation targets is not specified.

### Actual ranked suggestions

Quote/identity-grounded assessments: 58/64; strict accepted ranked items: 0/15.
These counts measure output grounding/conformance, not strategic or semantic accuracy.

1. **Ashnod's Altar** — core
   - A free repeatable sacrifice outlet turns any creature into two mana, fuels Meren experience, enables death triggers, and pays toward recasting/redeploying creatures.
   - Caveat: Produces only colorless mana and requires creatures to sacrifice.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C14 — Ashnod's Altar`.
2. **Phyrexian Altar** — core
   - A free repeatable sacrifice outlet converts creatures into colored mana, enabling death triggers and Meren experience while helping cast Golgari spells and redeploy creatures.
   - Caveat: Requires creatures to sacrifice and produces only one mana per creature.
   - Own independent shortlist: no; channels: gpt-5.6-luna:independent_shortlist.
   - Original invalid ranking identifier: `C54 — Phyrexian Altar`.
3. **Viscera Seer** — core
   - A zero-mana repeatable sacrifice outlet lets you cash in creatures at will, gain Meren experience, trigger death payoffs, and improve draw quality through scrying.
   - Caveat: Provides selection rather than mana, cards, or removal.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C17 — Viscera Seer`.
4. **Yawgmoth, Thran Physician** — core
   - A repeatable sacrifice outlet turns creatures into cards while shrinking targets; its proliferate ability can increase Meren's experience counters and other counters.
   - Caveat: The outlet costs 1 life and cannot sacrifice Yawgmoth; proliferate also needs a card to discard.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C48 — Yawgmoth, Thran Physician`.
5. **Stitcher's Supplier** — core
   - Mills three on both entry and death, rapidly filling Meren's graveyard while being excellent one-mana sacrifice fodder that supplies experience.
   - Caveat: Milling is not selective and can put noncreature cards into the graveyard.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C16 — Stitcher's Supplier`.
6. **Spore Frog** — core
   - A one-mana repeatable combat-damage prevention piece: sacrifice it to survive combat, gain Meren experience, then return it each end step.
   - Caveat: Only prevents combat damage for one turn and needs Meren plus sufficient experience for recursion.
   - Own independent shortlist: no; channels: diagnostic, gpt-5.6-luna:independent_shortlist.
   - Original invalid ranking identifier: `C34 — Spore Frog`.
7. **Drivnod, Carnage Dominus** — core
   - Each qualifying death trigger from your permanents triggers twice, including Meren's experience trigger; it also doubles death-payoff and card-draw creatures.
   - Caveat: Costs five mana; its protection ability exiles three creature cards from your graveyard.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C01 — Drivnod, Carnage Dominus`.
8. **Zulaport Cutthroat** — core
   - Every one of your creature deaths drains each opponent and gains life, providing an efficient multiplayer payoff for sacrifice fodder and Meren recursion.
   - Caveat: It only triggers from your creatures, not opponents' creatures.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C62 — Zulaport Cutthroat`.
9. **Blood Artist** — core
   - Every creature death becomes targeted life drain and life gain, giving the sacrifice-and-recursion engine a direct closing payoff.
   - Caveat: Targets one player rather than draining each opponent.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C29 — Blood Artist`.
10. **Reclamation Sage** — core
   - Reusable ETB artifact/enchantment removal is exactly what Meren can return each end step after it is sacrificed or dies.
   - Caveat: Requires a legal artifact or enchantment target when its ETB resolves.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C08 — Reclamation Sage`.
11. **Grist, Voracious Larva // Grist, the Plague Swarm** — core
   - Meren returning or you casting a creature from the graveyard can transform Grist; its planeswalker then creates fodder, mills targets, removes artifacts/enchantments, or copies graveyard creatures.
   - Caveat: Transformation requires Grist on the battlefield and a creature entering from or cast from your graveyard, plus {G}.
   - Own independent shortlist: no; channels: gpt-5.6-luna:independent_shortlist.
   - Original invalid ranking identifier: `C40 — Grist, Voracious Larva`.
12. **Twilight Diviner** — core
   - It surveils to stock the graveyard, then once each turn turns Meren's reanimated creature into a copy token, multiplying ETB bodies and future sacrifice fodder.
   - Caveat: The copy trigger is limited to once each turn and requires another creature entering or being cast from a graveyard.
   - Own independent shortlist: no; channels: gpt-5.6-luna:independent_shortlist.
   - Original invalid ranking identifier: `C46 — Twilight Diviner`.
13. **Sakura-Tribe Elder** — core
   - It ramps by sacrificing itself, immediately triggering Meren experience; later Meren recursion turns it into repeatable basic-land ramp.
   - Caveat: Finds only a basic land and puts it onto the battlefield tapped.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C37 — Sakura-Tribe Elder`.
14. **Shriekmaw** — core
   - Evoke provides cheap creature removal plus an immediate self-sacrifice for Meren experience; recurring it later repeatedly destroys eligible creatures.
   - Caveat: It cannot destroy artifact or black creatures, and evoke sacrifices it on entry.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C57 — Shriekmaw`.
   - Literal evidence failure: invalid_quote:C57.
15. **Cankerbloom** — core
   - It is cheap, sacrifice-based artifact/enchantment interaction; its alternate proliferate mode can increase Meren's experience counters and other counter resources.
   - Caveat: Must be sacrificed for either mode, and proliferate only adds counters already present.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C55 — Cankerbloom`.
   - Literal evidence failure: invalid_quote:C55.

## Saheeli / gpt-5.6-luna

### Planning intentions

- Build a dense Artificer/artifact casting engine that generates energy incidentally while advancing the board.
- Convert temporary 5/5 hasty copies into value through strong enter-the-battlefield, attack, death, sacrifice, or artifact-count triggers.
- Prioritize permanent copy targets whose abilities remain useful despite the temporary token's fixed 5/5 body and sacrifice clause.
- Support sustained energy production and spending without relying only on Saheeli's once-per-combat activation.
- Use combat payoffs that reward hasty attackers, artifact creatures, tokens, temporary creatures, or power-based damage.
- Include interaction and protection that preserve Saheeli, key artifacts, and valuable copy targets.

### Actual executable searches

1. **Find additional energy production attached to artifacts or creatures, preferably repeatable or triggered by casting and battlefield activity.**
   - Filters: `{"oracle_text_all": ["energy"], "oracle_text_any": ["get", "energy counter", "pay"], "type_line_any": ["Artifact", "Creature"]}`
   - 80 matches; 8 sampled.
2. **Find cheap Artificers that help sustain Saheeli's energy engine while providing useful bodies or artifact synergy.**
   - Filters: `{"type_line_any": ["Artificer"], "mana_value_max": 3.0}`
   - 96 matches; 8 sampled.
3. **Find artifact permanents with strong enter-the-battlefield or cast triggers to copy for immediate value.**
   - Filters: `{"oracle_text_all": ["When"], "oracle_text_any": ["enters the battlefield", "enters"], "type_line_any": ["Artifact"], "mana_value_min": 2.0, "mana_value_max": 7.0}`
   - 509 matches; 8 sampled.
4. **Find artifact creatures and permanents that reward attacking, especially when temporary hasty copies can amplify combat.**
   - Filters: `{"oracle_text_any": ["attacks", "whenever you attack", "combat"], "type_line_any": ["Artifact", "Creature"]}`
   - 1822 matches; 8 sampled.
5. **Find sacrifice outlets or death-trigger payoffs that can retain value from Saheeli's copy before its delayed sacrifice.**
   - Filters: `{"oracle_text_any": ["sacrifice", "dies", "when this creature dies"], "type_line_any": ["Artifact", "Creature", "Enchantment"]}`
   - 2199 matches; 8 sampled.
6. **Find artifact-token and creature-token payoffs that scale with repeated copied artifacts and artifact bodies.**
   - Filters: `{"oracle_text_any": ["artifact token", "create a token", "tokens"], "type_line_any": ["Artifact", "Creature", "Enchantment"]}`
   - 446 matches; 8 sampled.
7. **Find ways to protect or recur Saheeli and important artifact permanents while remaining within Temur colors.**
   - Filters: `{"oracle_text_any": ["hexproof", "indestructible", "return"], "type_line_any": ["Artifact", "Instant", "Enchantment"]}`
   - 667 matches; 8 sampled.
8. **Find power-based combat payoffs that benefit from temporary 5/5 artifact creature copies and hasty attacks.**
   - Filters: `{"oracle_text_any": ["power"], "type_line_any": ["Creature", "Enchantment", "Artifact"]}`
   - 1071 matches; 8 sampled.

**Nominated names:** Aetherworks Marvel; Bristly Bill, Spine Sower; Reckless Fireweaver; Marionette Master; Gonti's Aether Heart; Whirler Virtuoso; Retrofitter Foundry; Efficient Construction; Academy Manufactor; Daretti, Scrap Savant; Jhoira, Weatherlight Captain; Sai, Master Thopterist.

**Rejected nominations:** [{"name": "Marionette Master", "error": "off_color"}].

**Model-stated uncertainty:**
- The commander’s copy effect copies the target permanent’s copiable characteristics, then adds artifact creature, 5/5, and haste; exact value depends on whether the copied permanent has a strong enters-the-battlefield ability, attack trigger, static ability, or activated ability.
- The copied token is sacrificed at the next end step, but it is unclear whether the intended build should emphasize sacrificing it earlier; sacrifice outlets and death payoffs are therefore useful hypotheses rather than guaranteed inclusions.
- Energy cards vary substantially in whether they produce, store, or spend energy, and Saheeli’s ability requires three energy at the beginning of combat; the engine should be checked for timing compatibility.
- No budget, power level, combo, or card-pool restrictions were provided, so candidate selection intentionally mixes efficient staples with thematic options.

### Actual ranked suggestions

Quote/identity-grounded assessments: 55/64; strict accepted ranked items: 12/15.
These counts measure output grounding/conformance, not strategic or semantic accuracy.

1. **Izzet Generatorium** — core
   - Adds one extra energy to every gain, accelerating Saheeli, modules, and energy activations; four energy spent or lost unlocks repeatable card draw.
   - Caveat: Its draw ability needs four energy paid or lost that turn and tapping; it does not multiply existing energy.
   - Own independent shortlist: no; channels: diagnostic.
   - Literal evidence failure: invalid_quote:C60.
2. **Panharmonicon** — core
   - Doubles Saheeli's artifact/creature-entry triggers and the ETB triggers of copied artifact creatures, multiplying energy, cards, tokens, and removal.
   - Caveat: Only doubles triggered abilities caused by artifact or creature entries; it is not itself an artifact creature.
   - Own independent shortlist: no; channels: diagnostic.
3. **Fabrication Module** — core
   - Every energy gain puts a counter on a creature, turning Saheeli's energy engine into permanent combat growth; its activated ability supplies more energy.
   - Caveat: Needs creatures for targets and four mana plus tapping for its manual energy ability.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
   - Literal evidence failure: invalid_quote:C23.
4. **Gonti's Aether Heart** — core
   - Generates substantial energy from every artifact entry and converts eight energy into an extra turn; Saheeli's artifact casting and copy effects help both plans.
   - Caveat: Six mana and the extra turn exiles this artifact; needs sustained artifact entries.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist.
   - Literal evidence failure: invalid_quote:C00.
5. **Aetherworks Marvel** — core
   - Permanent deaths generate energy and six energy casts a top-six spell free; Saheeli's temporary copies and sacrifice effects provide deaths for the engine.
   - Caveat: Requires six energy and tapping; the free spell is limited to the top six cards.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
6. **Whirler Virtuoso** — core
   - Converts three energy into evasive artifact tokens, supplying combat bodies and targets for copy effects; its ETB energy is doubled by relevant support.
   - Caveat: Token production consumes the same energy Saheeli needs for copying.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
7. **Sai, Master Thopterist** — core
   - Turns every artifact cast into an evasive artifact token and sacrifices two artifacts for cards; Saheeli supplies more artifact spells and copy targets.
   - Caveat: The draw ability needs two expendable artifacts and four mana total.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
8. **Forensic Gadgeteer** — core
   - Artifact casts create Clues for cards, while reducing artifact activation costs improves energy-adjacent artifacts, Clues, and token engines.
   - Caveat: The reduction cannot make an activation's mana component less than one.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
9. **Shuri, Wakandan Inventor** — core
   - Reduces artifact spell costs and repeatedly turns one artifact into a copy of another, directly advancing artifact and copy value.
   - Caveat: Copy activation is sorcery-speed and requires two artifacts plus one mana.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
10. **Doubling Season** — core
   - Doubles Saheeli's copy tokens and artifact-token production, while doubling +1/+1 counters from Fabrication Module and similar support.
   - Caveat: Five mana and does not double energy counters, which are counters on a player.
   - Own independent shortlist: no; channels: diagnostic.
11. **Mirage Mockery** — core
   - Creates copies of artifact creatures and other creatures, with entwine producing both; it supplies broad copy density alongside Saheeli's combat copies.
   - Caveat: Entwine requires an additional five mana total for both modes.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
12. **Efficient Construction** — core
   - Each artifact spell creates an artifact flying attacker and triggers Saheeli's energy ability, strongly multiplying artifact-cast value.
   - Caveat: Four-mana nonartifact permanent does not itself generate energy.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
13. **Decoction Module** — core
   - Every creature entry supplies energy, while its bounce ability reuses ETB creatures and can save Saheeli's temporary copies before sacrifice.
   - Caveat: Bounce costs four mana and requires tapping; it cannot return artifacts that are not creatures.
   - Own independent shortlist: no; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
14. **Enthusiastic Mechanaut** — core
   - Reduces artifact spell costs, letting the deck cast more artifact and Artificer spells for energy, triggers, and artifact-token production.
   - Caveat: Only reduces artifact spells, not artifact activations or nonartifact spells.
   - Own independent shortlist: no; channels: gpt-5.6-terra:independent_shortlist.
15. **Academy Manufactor** — support
   - Clues from artifact-cast engines become Clue, Food, and Treasure, multiplying artifact tokens, card access, life, and mana; it also benefits existing Food/Clue production.
   - Caveat: Requires Clue, Food, or Treasure creation; it does not multiply Thopters or copies.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist.

## Saheeli / gpt-5.6-terra

### Planning intentions

- Use artifact and Artificer casts as the primary energy cadence, with repeatable energy producers bridging toward three energy each combat.
- Treat Saheeli’s temporary copies as ETB, attack, and death-trigger vehicles; favor targets that leave behind durable material or immediate value.
- Convert the copied 5/5 haste bodies into combat pressure and artifact-token volume, then leverage those tokens for further payoffs.
- Include nonlegendary copy targets or ways to profit immediately from legendary targets, since the legend rule can limit copied legends.

### Actual executable searches

1. **Find broad energy production and spending infrastructure for sustained activation of Saheeli.**
   - Filters: `{"oracle_text_all": ["{E}"]}`
   - 100 matches; 8 sampled.
2. **Find artifacts that reward or trigger from the artifact spells that fuel Saheeli's energy generation.**
   - Filters: `{"oracle_text_all": ["Whenever you cast an artifact spell"]}`
   - 18 matches; 8 sampled.
3. **Find Artificer-cast rewards that make the commander’s alternate trigger path worthwhile.**
   - Filters: `{"oracle_text_all": ["Whenever you cast an Artificer spell"]}`
   - 0 matches; 0 sampled.
4. **Find artifact permanents with enter-the-battlefield value that Saheeli can repeatedly copy for immediate returns.**
   - Filters: `{"oracle_text_all": ["enters the battlefield"], "type_line_any": ["Artifact"]}`
   - 0 matches; 0 sampled.
5. **Find artifact creatures whose death triggers turn an end-step-sacrificed Saheeli copy into retained value.**
   - Filters: `{"oracle_text_all": ["dies"], "type_line_any": ["Artifact", "Creature"]}`
   - 478 matches; 8 sampled.
6. **Find artifact creatures with attack triggers or attack-based output for Saheeli’s hasty copies.**
   - Filters: `{"oracle_text_all": ["attacks"], "type_line_any": ["Artifact", "Creature"]}`
   - 960 matches; 8 sampled.
7. **Find effects that create token copies, supplying redundant copy engines and token-density support.**
   - Filters: `{"oracle_text_all": ["token that's a copy"]}`
   - 192 matches; 8 sampled.
8. **Find artifact-spell cost reducers so more spells can be cast per turn to build energy and board presence.**
   - Filters: `{"oracle_text_all": ["artifact spells you cast cost"]}`
   - 5 matches; 5 sampled.

**Nominated names:** Decoction Module; Fabrication Module; Aetherworks Marvel; Whirler Virtuoso; Sai, Master Thopterist; Reckless Fireweaver; Solemn Simulacrum; Wurmcoil Engine; Myr Battlesphere; Meteor Golem; Triplicate Titan; Brudiclad, Telchor Engineer.

**Model-stated uncertainty:**
- The literal searches will not distinguish one-shot energy bursts from repeatable engines; resulting cards need rate and timing review.
- Saheeli can copy any permanent, not only artifacts, so strong Temur nonartifact ETB/death targets may merit a later pass.
- A copied legendary permanent normally creates a legend-rule decision; whether that is acceptable depends on its immediate ETB or death value.

### Actual ranked suggestions

Quote/identity-grounded assessments: 46/64; strict accepted ranked items: 0/15.
These counts measure output grounding/conformance, not strategic or semantic accuracy.

1. **Izzet Generatorium** — core
   - Every energy event, especially Saheeli's artifact/Artificer casts, gains one extra energy; this makes three-energy combat copies much more sustainable.
   - Caveat: Its card draw requires paying or losing four energy in one turn, not merely accumulating it.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C60 — Izzet Generatorium`.
   - Literal evidence failure: invalid_quote:C60.
2. **Whirler Virtuoso** — core
   - Artificer casting earns Saheeli energy and its ETB adds three more; surplus energy becomes evasive artifact tokens for copying and combat.
   - Caveat: Each Thopter consumes the same three-energy resource Saheeli needs at combat.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C08 — Whirler Virtuoso`.
   - Literal evidence failure: invalid_quote:C08.
3. **Decoction Module** — core
   - Every Saheeli copy and creature token produces energy; its bounce can reuse creature ETBs such as energy producers or protect a creature.
   - Caveat: The bounce costs four mana and returns the creature to hand rather than directly replaying it.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C05 — Decoction Module`.
   - Literal evidence failure: invalid_quote:C05.
4. **Doubling Season** — core
   - Doubles Saheeli's copy tokens and every artifact-token maker; it also doubles +1/+1 counters from Fabrication Module or Hangarback effects.
   - Caveat: At five mana it needs token or counter production already established to pay off.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C29 — Doubling Season`.
5. **Sundial of the Infinite** — core
   - Ending the turn with Saheeli's end-step sacrifice trigger on the stack exiles that trigger, preserving a valuable copy; it also has defensive timing utility.
   - Caveat: It can activate only during your turn and ending the turn also ends your remaining turn actions.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C46 — Sundial of the Infinite`.
6. **Brudiclad, Telchor Engineer** — core
   - Makes a hasty artifact token each combat, then can turn the token army into Saheeli's best copied token; universal haste converts the board immediately.
   - Caveat: Costs six and needs multiple tokens plus a desirable token copy to maximize the transformation.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C06 — Brudiclad, Telchor Engineer`.
7. **Inventor's Axe** — core
   - One-mana artifact casting earns Saheeli energy, while its ETB adds two more—exactly three total to activate Saheeli at combat; flash improves timing.
   - Caveat: The attached +2/+0 is minor, and re-equipping consumes the same energy resource.
   - Own independent shortlist: no; channels: gpt-5.6-luna:independent_shortlist.
   - Original invalid ranking identifier: `C38 — Inventor's Axe`.
   - Literal evidence failure: invalid_quote:C38.
8. **Second Harvest** — core
   - Duplicates every existing token, multiplying Saheeli copies and artifact-token payoffs; copied artifact tokens also amplify artifact-entry and sacrifice packages.
   - Caveat: Requires tokens already on the battlefield and costs four mana without creating the first one.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C04 — Second Harvest`.
9. **Aetherworks Marvel** — core
   - Sacrificed temporary Saheeli copies yield energy, which converts into free casts from six cards; artifact/token deaths further fuel it.
   - Caveat: The activation requires both tapping Marvel and six energy, with no guarantee the six cards contain a desired spell.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C37 — Aetherworks Marvel`.
   - Literal evidence failure: invalid_quote:C37.
10. **Sai, Master Thopterist** — core
   - Artifact casts both make Thopters and trigger Saheeli's energy ability; spare artifact tokens can become cards through its sacrifice outlet.
   - Caveat: Drawing requires two artifacts each time, so it competes with token-based combat and copy plans.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C11 — Sai, Master Thopterist`.
11. **Forensic Gadgeteer** — core
   - Artifact casts trigger Saheeli, investigate for artifact bodies/card draw, and reduce activation costs of clues, Foundry, and other artifacts.
   - Caveat: The cost reduction cannot reduce an activation below one mana and needs artifacts with mana activations.
   - Own independent shortlist: yes; channels: gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C20 — Forensic Gadgeteer`.
12. **Hangarback Walker** — core
   - An artifact cast for Saheeli, scalable counter sink, and death converts its counters into artifact Thopters for token and combat payoffs.
   - Caveat: It requires mana investment and must die to produce Thopters.
   - Own independent shortlist: no; channels: diagnostic.
   - Original invalid ranking identifier: `C45 — Hangarback Walker`.
13. **Myr Battlesphere** — core
   - An artifact cast triggers Saheeli; copying it produces four lasting artifact Myr, and attacks can convert those Myr into direct damage.
   - Caveat: The original costs seven mana, and the attack payoff requires untapped Myr.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C54 — Myr Battlesphere`.
14. **Wurmcoil Engine** — core
   - An artifact spell for Saheeli, a powerful 6/6 copy target, and a temporary copied token dying leaves two artifact Wurms behind.
   - Caveat: Six mana is substantial, and the death payoff needs the copied or original Wurm to die.
   - Own independent shortlist: yes; channels: diagnostic, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C26 — Wurmcoil Engine`.
15. **Reckless Fireweaver** — core
   - Every artifact token and artifact permanent entering becomes damage to every opponent, converting Saheeli copies and artifact-token production into a win payoff.
   - Caveat: It needs repeated artifact entries and is vulnerable as a 1/3 creature.
   - Own independent shortlist: yes; channels: gpt-5.6-luna:independent_shortlist, gpt-5.6-terra:independent_shortlist.
   - Original invalid ranking identifier: `C57 — Reckless Fireweaver`.
