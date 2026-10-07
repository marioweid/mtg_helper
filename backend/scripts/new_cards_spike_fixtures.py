"""Public, hand-authored deck fixtures and historical controls for a diagnostic spike.

Lists are not imported from users. Card facts are resolved against the downloaded Scryfall
catalog. These are controlled test decks, not claims of optimized tournament lists.
"""

ALELA_CORE = """
Sol Ring|Arcane Signet|Commander's Sphere|Fellwar Stone|Mind Stone|Thought Vessel|
Swords to Plowshares|Path to Exile|Counterspell|Arcane Denial|Negate|Dovin's Veto|
Anguished Unmaking|Despark|Mortify|Generous Gift|Feed the Swarm|Read the Bones|
Fact or Fiction|Night's Whisper|Sign in Blood|Painful Truths|Damn|Wrath of God|
Austere Command|Swan Song|Reality Shift|Wash Away|Return to Dust|Vindicate
"""

ARTIFACTS = """
Azorius Signet|Dimir Signet|Orzhov Signet|Talisman of Dominance|Talisman of Hierarchy|
Talisman of Progress|Thoughtcast|Thought Monitor|Emry, Lurker of the Loch|
Shimmer Dragon|Master of Etherium|Steel Overseer|Tempered Steel|Efficient Construction|
Thopter Spy Network|Sharding Sphinx|Foundry Inspector|Jhoira's Familiar|Solemn Simulacrum|
Myr Retriever|Junk Diver|Scrap Trawler|Ichor Wellspring|Mycosynth Wellspring|Soul-Guide Lantern|
Executioner's Capsule|Dispeller's Capsule|Nihil Spellbomb|Chromatic Star|Chromatic Sphere|
Wayfarer's Bauble|Welding Jar
"""

ENCHANTMENTS = """
Omen of the Sea|Omen of the Sun|Omen of the Dead|Oblivion Ring|Banishing Light|Grasp of Fate|
Darksteel Mutation|Imprisoned in the Moon|Seal of Cleansing|Seal of Removal|Seal of Doom|
Ghostly Prison|Propaganda|Sphere of Safety|Hallowed Haunting|Sigil of the Empty Throne|
Starfield of Nyx|Dance of the Manse|Open the Vaults|Resurgent Belief|Underworld Connections|
Phyrexian Arena|Monastery Siege|Bident of Thassa|Reconnaissance Mission|Coastal Piracy|
Court of Grace|Court of Cunning|Court of Ambition|Intangible Virtue|Favorable Winds|Doomwake Giant
"""

CAMELLIA = """
Sol Ring|Arcane Signet|Golgari Signet|Talisman of Resilience|Fellwar Stone|Nature's Lore|
Rampant Growth|Cultivate|Kodama's Reach|Sakura-Tribe Elder|Elvish Mystic|Llanowar Elves|
Fyndhorn Elves|Gilded Goose|Tough Cookie|Gingerbrute|Feasting Troll King|Witch's Oven|
Cauldron Familiar|Experimental Confectioner|Tireless Provisioner|Trail of Crumbs|
Insidious Roots|Night of the Sweets' Revenge|The Underworld Cookbook|Candy Trail|
Many Partings|Bakersbane Duo|Honored Dreyleader|Scavenger's Talent|Vinereap Mentor|
Greta, Sweettooth Scourge|Welcome to Sweettooth|Pawpatch Formation|Heaped Harvest|
Bake into a Pie|Feed the Cauldron|Sweettooth Witch|Gumdrop Poisoner|Savvy Hunter|
Gluttonous Troll|Ravenous Squirrel|Nadier's Nightblade|Zulaport Cutthroat|Blood Artist|
Bastion of Remembrance|Viscera Seer|Carrion Feeder|Deadly Dispute|Village Rites|
Plumb the Forbidden|Morbid Opportunist|Skullclamp|Beast Within|Putrefy|Go for the Throat|
Infernal Grasp|Tragic Slip|Toxic Deluge|Victimize|Reclamation Sage|Eternal Witness
"""

TALRAND = """
Sol Ring|Arcane Signet|Mind Stone|Thought Vessel|Sky Diamond|Sapphire Medallion|
Ponder|Preordain|Brainstorm|Opt|Consider|Serum Visions|Sleight of Hand|Impulse|
Frantic Search|Fact or Fiction|Deep Analysis|Think Twice|Behold the Multiverse|
Treasure Cruise|Dig Through Time|Flow of Knowledge|Thirst for Discovery|Chemister's Insight|
Counterspell|Arcane Denial|Negate|Disdainful Stroke|Essence Scatter|Exclude|
Dissolve|Dissipate|Sinister Sabotage|Rewind|Unwind|Wash Away|Swan Song|An Offer You Can't Refuse|
Rapid Hybridization|Pongify|Reality Shift|Resculpt|Ravenform|Into the Roil|Blink of an Eye|
Aetherize|Aetherspouts|Evacuation|Whelming Wave|Echoing Truth|Snap|Unsubstantiate|
Murmuring Mystic|Docent of Perfection|Wavebreak Hippocamp|Baral, Chief of Compliance|
Goblin Electromancer|Curious Homunculus|Reconnaissance Mission|Coastal Piracy|
Bident of Thassa|Favorable Winds|Windstorm Drake
"""
# Electromancer is deliberately omitted: a familiar spellslinger card is illegal in mono-blue.
TALRAND = TALRAND.replace("Goblin Electromancer|", "")

DECKS = [
    {
        "id": "alela-artifacts",
        "commander": "Alela, Artful Provocateur",
        "goal": "Artifact-cast engine and evasive Faerie tokens; no infinite combos.",
        "spells": ALELA_CORE + "|" + ARTIFACTS,
        "basics": {"Island": 15, "Plains": 11, "Swamp": 11},
    },
    {
        "id": "alela-enchantments",
        "commander": "Alela, Artful Provocateur",
        "goal": "Enchantment-cast engine, pillowfort and Faerie tokens; no infinite combos.",
        "spells": ALELA_CORE + "|" + ENCHANTMENTS,
        "basics": {"Island": 13, "Plains": 14, "Swamp": 10},
    },
    {
        "id": "camellia-food",
        "commander": "Camellia, the Seedmiser",
        "goal": "Food creation/sacrifice, Squirrel tokens and drain; no infinite combos.",
        "spells": CAMELLIA,
        "basics": {"Forest": 21, "Swamp": 16},
    },
    {
        "id": "talrand-spells",
        "commander": "Talrand, Sky Summoner",
        "goal": "Cast many cheap instants/sorceries, protect Talrand, win with Drake tokens.",
        "spells": TALRAND,
        "basics": {"Island": 37},
    },
]

# These labels test broad compatibility, not subjective claims of the optimal cut.
# Expectations never appear in model input. Historical controls bypass age only for evaluation.
CONTROLS = {
    "alela-artifacts": {
        "Sai, Master Thopterist": ["strong"],
        "Vedalken Archmage": ["strong"],
        "Etherium Sculptor": ["strong", "worth_testing"],
        "Mesa Enchantress": ["reject", "worth_testing"],
        "Eidolon of Blossoms": ["reject"],
        "Sol Ring": ["reject"],
    },
    "alela-enchantments": {
        "Mesa Enchantress": ["strong"],
        "Archon of Sun's Grace": ["strong"],
        "Sai, Master Thopterist": ["reject", "worth_testing"],
        "Vedalken Archmage": ["reject", "worth_testing"],
        "Eidolon of Blossoms": ["reject"],
        "Sol Ring": ["reject"],
    },
    "camellia-food": {
        "Academy Manufactor": ["strong"],
        "Peregrin Took": ["strong"],
        "Mirkwood Bats": ["strong"],
        "Ashnod's Altar": ["reject", "worth_testing", "strong"],
        "Eidolon of Blossoms": ["reject", "worth_testing"],
        "Anointed Procession": ["reject"],
    },
    "talrand-spells": {
        "Archmage Emeritus": ["strong"],
        "Metallurgic Summonings": ["strong"],
        "Mystic Sanctuary": ["strong", "worth_testing"],
        "Panharmonicon": ["reject"],
        "Harmonic Prodigy": ["reject"],
        "Deadly Dispute": ["reject"],
    },
}
