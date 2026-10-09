# Actual Sol planning outputs — partial run

Both planning requests completed. Meren assessment timed out; Saheeli assessment was not sent.
No recommendations/assessment judgments were received. These are plans and local discoveries,
not certified strategic advice. [README.md](README.md) records spending and limitations.

## Meren

Planning: 33.1 seconds; $0.015838 conservative estimate.

### Intentions

- Use repeatable sacrifice outlets and expendable creatures to build experience while controlling when death effects happen.
- Prioritize low-mana-value utility creatures for early battlefield recursion; higher-value targets still provide cards through Meren's hand-return fallback.
- Reuse entry and death interaction, remembering that Meren returns creatures rather than casting them.
- Convert sacrificed bodies into mana, cards, and replacement bodies to sustain the value engine.
- Fill the graveyard selectively and add independent recursion so the deck retains value without Meren.
- Sacrifice useful creatures before the end-step trigger to establish targets and reach experience thresholds; token deaths also generate experience while Meren is present.

### Generated searches and actual source results

1. **Find sacrifice outlets that let the deck choose when creatures die; inspect activation costs and timing restrictions.**
   - `{"oracle_text_any": ["Sacrifice a creature", "Sacrifice another creature"]}`
   - 340 matches; 8 sampled.
2. **Find cheap death-effect creatures that can be returned to the battlefield with few experience counters.**
   - `{"oracle_text_all": ["dies"], "type_line_any": ["Creature"], "mana_value_max": 3.0}`
   - 299 matches; 8 sampled.
3. **Find reusable creature-based interaction associated with entering the battlefield.**
   - `{"oracle_text_all": ["enters"], "oracle_text_any": ["destroy target", "exile target", "sacrifices a creature", "sacrifices a permanent"], "type_line_any": ["Creature"]}`
   - 144 matches; 8 sampled.
4. **Find creatures that stock the graveyard while remaining potential sacrifice and recursion targets.**
   - `{"oracle_text_any": ["mill", "into your graveyard"], "type_line_any": ["Creature"], "mana_value_max": 4.0}`
   - 230 matches; 8 sampled.
5. **Find creature-based token production to supply expendable bodies and increase deaths per recursion cycle.**
   - `{"oracle_text_all": ["create", "token"], "type_line_any": ["Creature"]}`
   - 718 matches; 8 sampled.
6. **Find death-triggered payoffs that convert the sacrifice engine into additional resources or pressure.**
   - `{"oracle_text_all": ["whenever"], "oracle_text_any": ["creature dies", "creature you control dies", "one or more creatures"]}`
   - 201 matches; 8 sampled.
7. **Find sacrificial utility creatures that turn themselves or other bodies into mana or searched resources.**
   - `{"oracle_text_all": ["sacrifice"], "oracle_text_any": ["add ", "search your library"], "type_line_any": ["Creature"], "mana_value_max": 3.0}`
   - 97 matches; 8 sampled.
8. **Find independent creature recovery to preserve access to utility bodies when Meren is unavailable.**
   - `{"oracle_text_any": ["return target creature card", "return a creature card", "return all creature cards"]}`
   - 199 matches; 8 sampled.

**Initial nominations:** Viscera Seer; Carrion Feeder; Sakura-Tribe Elder; Spore Frog; Plaguecrafter; Fleshbag Marauder; Shriekmaw; Eternal Witness; Skullclamp; Pitiless Plunderer; Stitcher's Supplier; Living Death.

### Independent local shortlist

1. Viscera Seer
2. Silumgar Butcher
3. Carrion Feeder
4. Innocuous Rat
5. Sakura-Tribe Elder
6. Anthropede
7. Spore Frog
8. Six
9. Plaguecrafter
10. Brightcap Badger // Fungus Frolic
11. Fleshbag Marauder
12. The Cauldron of Eternity
13. Shriekmaw
14. Redrock Sentinel
15. Eternal Witness
16. Altar of Bhaal // Bone Offering
17. Skullclamp
18. Fallen Ideal
19. Pitiless Plunderer
20. Wriggling Grub
21. Stitcher's Supplier
22. Loathsome Curator
23. Living Death
24. Morgue Thrull
25. Twitching Doll
26. Avacyn, Angel of Horror
27. Canoptek Wraith
28. Tyvar, Jubilant Brawler
29. Grisly Sigil
30. Mister Gutsy
31. Alpha Deathclaw
32. Skola Grovedancer

### Model-stated uncertainty

- Literal text searches produce hypotheses, not guaranteed interactions; inspect whose creatures die, whether effects require casting, and any timing or activation limits.
- Meren's battlefield-return threshold uses mana value, not discounted casting costs; expensive targets may initially return only to hand.
- The desired balance between attrition, combat pressure, and combo finishes is unspecified; no combo restriction is assumed.

## Saheeli

Planning: 37.5 seconds; $0.016502 conservative estimate.

### Intentions

- Generate at least three energy per turn through inexpensive artifact/Artificer casts and supplemental energy engines.
- Copy permanents with valuable entry, attack, or death abilities; Saheeli's tokens enter but are not cast.
- Turn temporary 5/5 attackers into lasting resources through death triggers, additional copies, or sacrifice outlets.
- Reduce artifact casting costs and multiply energy or token production to sustain the engine.
- Distinguish sacrifice from destruction: indestructible does not preserve Saheeli's tokens.

### Generated searches and actual source results

1. **Find supplemental energy producers, energy multipliers, and alternative energy outlets.**
   - `{"oracle_text_any": ["{E}"]}`
   - 100 matches; 8 sampled.
2. **Find inexpensive spells that trigger Saheeli while developing mana, cards, or utility.**
   - `{"type_line_any": ["Artifact", "Artificer"], "mana_value_max": 2.0}`
   - 1107 matches; 8 sampled.
3. **Find artifact copy targets and engines that produce value when permanents enter.**
   - `{"oracle_text_all": ["enters"], "type_line_any": ["Artifact"]}`
   - 720 matches; 8 sampled.
4. **Find artifact creatures whose death can convert an expiring copy into lasting value.**
   - `{"oracle_text_all": ["dies"], "type_line_any": ["Artifact"]}`
   - 109 matches; 8 sampled.
5. **Find copy targets with attack or combat-damage rewards that haste enables immediately.**
   - `{"oracle_text_any": ["whenever", "combat damage"], "type_line_any": ["Creature"], "mana_value_min": 5.0}`
   - 814 matches; 8 sampled.
6. **Find ways to preserve temporary value by ending the turn, populating, or sacrificing a token before its scheduled sacrifice.**
   - `{"oracle_text_any": ["end the turn", "populate", "sacrifice an artifact", "sacrifice a creature"]}`
   - 218 matches; 8 sampled.
7. **Find casting discounts that make repeated artifact casts and their energy triggers sustainable.**
   - `{"oracle_text_all": ["artifact spells", "cost"]}`
   - 7 matches; 7 sampled.
8. **Find token-production modifiers that can multiply Saheeli's combat copies or supporting resource tokens.**
   - `{"oracle_text_all": ["token"], "oracle_text_any": ["twice", "double", "additional"]}`
   - 113 matches; 8 sampled.

**Initial nominations:** Aether Refinery; Gonti's Aether Heart; Decoction Module; Whirler Virtuoso; Enthusiastic Mechanaut; Panharmonicon; Wurmcoil Engine; Triplicate Titan; Ancient Copper Dragon; Sundial of the Infinite; Brudiclad, Telchor Engineer; Academy Manufactor.

### Independent local shortlist

1. Aether Refinery
2. Plasma Caster
3. Gonti's Aether Heart
4. Feldon's Cane
5. Decoction Module
6. Relic Axe
7. Whirler Virtuoso
8. Lesser Masticore
9. Enthusiastic Mechanaut
10. Burly Breaker // Dire-Strain Demolisher
11. Panharmonicon
12. Towering Titan
13. Wurmcoil Engine
14. Saheeli, Filigree Master
15. Triplicate Titan
16. The Spear of Leonidas
17. Ancient Copper Dragon
18. Aether Chaser
19. Sundial of the Infinite
20. Smuggler's Copter
21. Brudiclad, Telchor Engineer
22. Hulldrifter
23. Academy Manufactor
24. Big Mother Mouser
25. Paleoloth
26. Metamorphosis
27. Armor Wars
28. Steampath Charger
29. Spontaneous Artist
30. Throne of Geth
31. Saheeli's Lattice // Mastercraft Raptor
32. Lockjaw Snapper

### Model-stated uncertainty

- The combat-reward search is deliberately broad; results require checking whether their triggers actually reward attacking or connecting.
- Legendary copy targets generally lose one copy to the legend rule unless another effect changes that outcome.
- Sundial requires timing around the delayed sacrifice trigger; extra token copies and Brudiclad transformations need individual rules review.
- No budget, power-level, or combo restriction is supplied, so expensive targets and potentially powerful engine interactions remain candidates.
