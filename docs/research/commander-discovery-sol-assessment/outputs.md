# Actual Sol assessment outputs

Two separately authorized assessment requests completed. Earlier timeout remains potentially billed.
These are actual model judgments, not certified Magic rulings. See [README.md](README.md).
Both cases use the unchanged Luna/Terra 64-card pools. All thirty ranking IDs were valid.

## Meren

Assessment: 153.4 s; $0.119027 conservative estimate.
Quote/identity-grounded rows: 64/64; complete frozen validation: True.
Grounding counts are not semantic-accuracy percentages.

1. **Viscera Seer** — core
   - Provides unrestricted, mana-free sacrifices for experience and death effects, while scry improves future draws. Meren can cheaply recover the outlet itself.
   - Caveat: Requires creatures to sacrifice; scry selects draws but does not draw cards.
   - Sol independently shortlisted: yes.
2. **Yawgmoth, Thran Physician** — core
   - Sacrifices fuel experience, draw, and optional creature weakening. Discard stocks recursion targets, while proliferate increases existing experience and useful permanent counters.
   - Caveat: Cannot sacrifice itself; life, fodder, and cards limit activations. Proliferate requires an experience counter already present.
   - Sol independently shortlisted: no.
3. **Sakura-Tribe Elder** — core
   - Self-sacrifice ramps and fixes mana while earning experience. Repeated Meren returns turn end steps into more basic lands without needing another outlet.
   - Caveat: Requires basic lands remaining in the library; lands enter tapped.
   - Sol independently shortlisted: yes.
4. **Phyrexian Altar** — core
   - Mana-free sacrifices trigger experience and death payoffs while fixing colors for further plays. It also supplies nonland green mana under proposed Contamination.
   - Caveat: Requires creature fodder and yields one mana per sacrifice; no repeatable infinite loop is established by Meren alone.
   - Sol independently shortlisted: no.
5. **Ashnod's Altar** — core
   - A mana-free, untapped sacrifice outlet produces experience and funds further plays. It converts spent entry-effect creatures or tokens into two mana apiece.
   - Caveat: Produces only colorless mana and needs expendable creatures; Meren's once-per-end-step return alone is not an infinite loop.
   - Sol independently shortlisted: no.
6. **Stitcher's Supplier** — core
   - Mills on entry and death to build recursion options while earning experience as fodder. Its one-mana value enables early Meren recycling.
   - Caveat: Mill is not selective and needs sufficient useful graveyard targets; deliberate repeat deaths require an outlet.
   - Sol independently shortlisted: yes.
7. **Eternal Witness** — core
   - Recurring entry recovers any card, extending Meren's engine to removal, lands, and noncreature infrastructure. Its spent body supplies sacrifice value and experience.
   - Caveat: Returns to hand rather than battlefield; recovered spells still require casting costs.
   - Sol independently shortlisted: yes.
8. **Plaguecrafter** — core
   - Recurring entry pressures every opponent's creatures or planeswalkers. Sacrificing itself satisfies your obligation, earns experience, and readies the next return.
   - Caveat: Opponents choose what to sacrifice; tokens can absorb it, and players without eligible permanents discard instead.
   - Sol independently shortlisted: yes.
9. **Twilight Diviner** — core
   - Surveil stocks and selects the graveyard; Meren's return of another creature creates an extra copy for entry effects or sacrifice fodder. Copies do not inherit counters.
   - Caveat: Cannot copy itself and triggers only once each turn; legendary copies need care. Only battlefield returns, not hand returns, qualify.
   - Sol independently shortlisted: no.
10. **Insidious Fungus** — core
   - Self-sacrifice earns experience and answers artifacts or enchantments. With no removal target needed, its other mode draws and can accelerate land deployment on repeated returns.
   - Caveat: Each activation costs two; land acceleration requires a land in hand.
   - Sol independently shortlisted: no.
11. **Reclamation Sage** — core
   - Repeated Meren returns destroy artifacts or enchantments; its spent body then fuels sacrifice and experience. Proposed Bellower can also fetch it.
   - Caveat: Needs a relevant target for removal value and an outlet to recycle it deliberately.
   - Sol independently shortlisted: no.
12. **Grim Haruspex** — core
   - Draws repeatedly from nontoken sacrifice fodder as Meren earns experience. Meren can recover the draw engine; morph offers an alternative deployment route.
   - Caveat: Does not draw for tokens, opponents' creatures, or its own death; morph requires extra mana beyond casting face up.
   - Sol independently shortlisted: no.
13. **Cankerbloom** — core
   - Self-sacrifice provides recurring artifact/enchantment removal and experience. Its proliferate mode can add another existing experience counter as well as useful permanent counters.
   - Caveat: Costs one per activation; proliferate cannot create the first experience counter without one present when it resolves.
   - Sol independently shortlisted: no.
14. **Zulaport Cutthroat** — core
   - Converts your sacrifice deaths into life loss for every opponent and life gain for you. Its own death also triggers, and Meren can cheaply recover the payoff.
   - Caveat: Does not trigger from opponents' creature deaths; needs your creatures dying to sustain pressure.
   - Sol independently shortlisted: no.
15. **Spore Frog** — core
   - Self-sacrifice earns experience while preventing combat damage. Meren can restore it at end step to repeat defensive coverage on a later turn.
   - Caveat: Does not stop noncombat damage or other win conditions; one end-step return does not cover every opponent's combat.
   - Sol independently shortlisted: yes.

### Failed/missing assessments

None.

## Saheeli

Assessment: 151.6 s; $0.123310 conservative estimate.
Quote/identity-grounded rows: 61/64; complete frozen validation: False.
Grounding counts are not semantic-accuracy percentages.

1. **Izzet Generatorium** — core
   - Adds one energy to every gain event, including Saheeli casts and entry engines. Spending four energy unlocks a card; a nonlegendary copy stacks another replacement.
   - Caveat: Saheeli's three-energy payment alone does not unlock drawing; the copied artifact must tap instead of attack to draw immediately.
   - Sol independently shortlisted: no.
2. **Decoction Module** — core
   - Every Saheeli copy enters as a creature and refunds one energy. Other creatures sustain the engine; bouncing entry-value creatures enables reuse and protection.
   - Caveat: Bounce costs four mana and a tap; entries, not artifact casts alone, fuel its trigger.
   - Sol independently shortlisted: yes.
3. **Whirler Virtuoso** — core
   - Artificer casting plus entry yields four energy with Saheeli. Each copy refunds its three-energy cost; spare energy creates flying artifact bodies for other engines.
   - Caveat: Thopter production competes with Saheeli for energy; tokens are not cast and do not trigger her cast ability.
   - Sol independently shortlisted: yes.
4. **Thought Monitor** — core
   - Artifact density discounts a cast that earns energy and draws two; each Saheeli copy draws two more and attacks as a flying 5/5.
   - Caveat: Needs substantial artifact density for efficient casting; affinity does not reduce the blue requirement.
   - Sol independently shortlisted: no.
5. **Myr Battlesphere** — core
   - Every copy leaves four permanent artifact Myr; its hasty attack can tap those fresh Myr for added power and direct damage, while their entries feed proposed engines.
   - Caveat: Seven mana to establish; Myr tapped for its attack ability cannot also attack that combat.
   - Sol independently shortlisted: no.
6. **Solemn Simulacrum** — core
   - Artifact casting fuels energy and entry ramps a basic; each Saheeli copy ramps again, attacks as a 5/5, and draws when sacrificed.
   - Caveat: Requires basic lands remaining in the library; ramped lands enter tapped.
   - Sol independently shortlisted: no.
7. **Gonti's Aether Heart** — core
   - Artifact entries generate sustained energy, including Saheeli's tokens; eight energy buys another turn and combat. A Heart copy triggers both Hearts before the legend rule applies.
   - Caveat: Costs six mana; copying it requires a legend-rule choice. Extra turns consume eight energy and exile a Heart, not an automatic loop.
   - Sol independently shortlisted: yes.
8. **Shuri, Wakandan Inventor** — core
   - Artificer casting earns energy and discounts future artifacts. Turning a spare artifact into a nonlegendary target lets Saheeli copy that template with its abilities.
   - Caveat: Requires two artifacts and sorcery timing; transformation itself causes no entry triggers, and a combat-created Shuri cannot activate then.
   - Sol independently shortlisted: no.
9. **Enthusiastic Mechanaut** — support
   - Reduces artifact costs to enable more energy-producing casts; its own artifact/Artificer cast triggers Saheeli once, and its flying copy can attack evasively.
   - Caveat: Only reduces generic mana, not colored costs; a spell being both artifact and Artificer does not trigger Saheeli twice.
   - Sol independently shortlisted: yes.
10. **Jhoira, Weatherlight Captain** — support
   - Artifact casts draw cards while fueling Saheeli; legendary spells including Saheeli also draw. Jhoira's own Artificer cast contributes energy.
   - Caveat: Token creation is not casting; a Saheeli copy of legendary Jhoira cannot simply coexist with the original.
   - Sol independently shortlisted: no.
11. **Wurmcoil Engine** — core
   - Artifact casting generates energy; a hasty 5/5 copy carries its combat keywords, then its sacrifice leaves two lasting artifact Wurms for future value.
   - Caveat: Six mana to establish the original; copied base stats are 5/5 rather than 6/6.
   - Sol independently shortlisted: yes.
12. **Sundial of the Infinite** — core
   - Ending the turn with Saheeli's sacrifice trigger on the stack exiles that one-shot trigger, retaining her copy. Its artifact cast also generates energy.
   - Caveat: Wait until the sacrifice trigger is on the stack; ending earlier merely postpones it. Costs one mana, a tap, and remaining turn actions.
   - Sol independently shortlisted: yes.
13. **Forensic Gadgeteer** — core
   - Artificer casting earns energy; artifact casts produce Clues for cards and artifact-entry engines. Discounts help Clues, Module bounce, and Foundry activations.
   - Caveat: Cannot reduce energy costs or Saheeli's triggered payment; artifact abilities retain a minimum one-mana cost.
   - Sol independently shortlisted: no.
14. **Inventor's Axe** — core
   - One mana yields three energy with Saheeli through cast and entry triggers. Flash can fund her combat payment; the original's attachment increases combat damage.
   - Caveat: Re-equipping spends two energy; a creature copy of the Equipment cannot remain attached.
   - Sol independently shortlisted: no.
15. **Reckless Fireweaver** — core
   - Artificer casting supplies energy; every Saheeli artifact copy damages all opponents. Proposed Thopter, Myr, and death-token packages multiply its triggers.
   - Caveat: Needs repeated artifact entries; copying Fireweaver itself produces modest damage without additional entries.
   - Sol independently shortlisted: no.

### Failed/missing assessments

- `C07` / Plasma Caster: invalid_quote:C07.
  Reason: Artifact casting gives energy, and equipped attacks provide two more for later combats. Its blocker ability offers a combat outlet alongside the power boost.
  Caveat: Attack energy arrives after Saheeli's combat trigger; equip costs two, and blocker exile depends on a coin flip.
- `C09` / Wheel of Potential: duplicate_assessment, missing_candidate_evidence.
  Reason: No supplied candidate has this key, so neither primary synergy nor secondary utility can be evaluated.
  Caveat: Candidate data is absent.
- `C09` / Wheel of Potential: duplicate_assessment, missing_candidate_evidence.
  Reason: No supplied candidate has this key.
  Caveat: Candidate data is absent.
- Missing `C63` / Torpor Orb.
