"""Tests for rule-based card tag classification."""

from mtg_helper.services.tag_service import classify_card, classify_token_types, classify_traits


def _classify(
    oracle_text: str = "",
    type_line: str = "Instant",
    name: str = "Test Card",
    keywords: list[str] | None = None,
    cmc: float | None = None,
) -> list[str]:
    return classify_card(name, type_line, oracle_text, keywords or [], cmc)


# ── ramp ──────────────────────────────────────────────────────────────────────


def test_ramp_tap_add_mana() -> None:
    tags = _classify("{T}: Add {G}.")
    assert "ramp" in tags


def test_ramp_search_library_for_land() -> None:
    tags = _classify("Search your library for a basic land card and put it onto the battlefield.")
    assert "ramp" in tags


def test_ramp_search_snow_land() -> None:
    tags = _classify("Search your library for a snow land card.")
    assert "ramp" in tags


# ── draw ──────────────────────────────────────────────────────────────────────


def test_draw_a_card() -> None:
    tags = _classify("Draw a card.")
    assert "draw" in tags


def test_draw_two_cards() -> None:
    tags = _classify("Draw two cards.")
    assert "draw" in tags


def test_draw_x_cards() -> None:
    tags = _classify("Draw X cards.")
    assert "draw" in tags


def test_each_player_draws() -> None:
    tags = _classify("Each player draws two cards.")
    assert "draw" in tags


# ── removal ───────────────────────────────────────────────────────────────────


def test_removal_destroy_target() -> None:
    tags = _classify("Destroy target creature.")
    assert "removal" in tags


def test_removal_exile_target() -> None:
    tags = _classify("Exile target artifact or enchantment.")
    assert "removal" in tags


def test_removal_damage_target_creature() -> None:
    tags = _classify("This spell deals 3 damage to target creature.")
    assert "removal" in tags


# ── board wipe ────────────────────────────────────────────────────────────────


def test_board_wipe_destroy_all() -> None:
    tags = _classify("Destroy all creatures.")
    assert "board_wipe" in tags


def test_board_wipe_exile_all() -> None:
    tags = _classify("Exile all artifacts and enchantments.")
    assert "board_wipe" in tags


def test_board_wipe_minus_all() -> None:
    tags = _classify("All creatures get -3/-3 until end of turn.")
    assert "board_wipe" in tags


# ── counterspell ──────────────────────────────────────────────────────────────


def test_counterspell_target_spell() -> None:
    tags = _classify("Counter target spell.")
    assert "counterspell" in tags


def test_counterspell_noncreature() -> None:
    tags = _classify("Counter target noncreature spell.")
    assert "counterspell" in tags


# ── tutor ─────────────────────────────────────────────────────────────────────


def test_tutor_search_library_non_land() -> None:
    tags = _classify("Search your library for a creature card and put it into your hand.")
    assert "tutor" in tags


def test_tutor_does_not_tag_land_search() -> None:
    # Land searches should be ramp, not tutor
    tags = _classify("Search your library for a basic land and put it onto the battlefield.")
    assert "tutor" not in tags


# ── token ─────────────────────────────────────────────────────────────────────


def test_token_create_a_token() -> None:
    tags = _classify("Create a 1/1 green Elf creature token.")
    assert "token" in tags


def test_token_create_x_tokens() -> None:
    tags = _classify("Create X 1/1 white Soldier creature tokens.")
    assert "token" in tags


# ── plus one counters ─────────────────────────────────────────────────────────


def test_plus_one_counters() -> None:
    tags = _classify("Put a +1/+1 counter on target creature.")
    assert "plus_one_counters" in tags


# ── lifegain ──────────────────────────────────────────────────────────────────


def test_lifegain_you_gain() -> None:
    tags = _classify("You gain 3 life.")
    assert "lifegain" in tags


# ── graveyard ─────────────────────────────────────────────────────────────────


def test_graveyard_return_from() -> None:
    tags = _classify("Return target creature card from your graveyard to your hand.")
    assert "graveyard" in tags


# ── sacrifice + aristocrats ───────────────────────────────────────────────────


def test_sacrifice_alone() -> None:
    tags = _classify("Sacrifice a creature: gain 2 life.")
    assert "sacrifice" in tags
    assert "aristocrats" not in tags


def test_aristocrats_sacrifice_and_death() -> None:
    tags = _classify(
        "Sacrifice a creature: draw a card. Whenever another creature dies, you gain 1 life."
    )
    assert "sacrifice" in tags
    assert "aristocrats" in tags


# ── equipment / voltron ───────────────────────────────────────────────────────


def test_equipment_tagged() -> None:
    tags = _classify(
        "Equipped creature gets +2/+2. Equip {2}.",
        type_line="Artifact — Equipment",
    )
    assert "equipment" in tags


def test_voltron_equipment() -> None:
    tags = _classify(
        "Equipped creature gets +3/+3 and has trample. Equip {3}.",
        type_line="Artifact — Equipment",
    )
    assert "voltron" in tags


def test_voltron_aura() -> None:
    tags = _classify(
        "Enchanted creature gets +2/+2 and has flying.",
        type_line="Enchantment — Aura",
    )
    assert "voltron" in tags


# ── fast mana ─────────────────────────────────────────────────────────────────


def test_fast_mana_sol_ring_by_name() -> None:
    tags = _classify("{T}: Add {C}{C}.", name="Sol Ring", cmc=1)
    assert "fast_mana" in tags


def test_fast_mana_low_cmc_mana_rock() -> None:
    # cmc ≤ 2, adds mana, classified as ramp → qualifies for fast_mana
    tags = _classify("{T}: Add {C}.", name="Some Signet", cmc=2)
    assert "fast_mana" in tags


def test_no_fast_mana_for_high_cmc() -> None:
    tags = _classify("{T}: Add {G}.", name="Some Mana Rock", cmc=4)
    assert "fast_mana" not in tags


# ── stax ──────────────────────────────────────────────────────────────────────


def test_stax_opponents_cant_cast() -> None:
    tags = _classify("Opponents can't cast spells on your turn.")
    assert "stax" in tags


def test_stax_costs_more() -> None:
    tags = _classify("Spells cost {2} more to cast.")
    assert "stax" in tags


# ── group hug ─────────────────────────────────────────────────────────────────


def test_group_hug_each_player_draws() -> None:
    tags = _classify("At the beginning of each player's upkeep, each player draws a card.")
    assert "group_hug" in tags


# ── blink ─────────────────────────────────────────────────────────────────────


def test_blink_exile_then_return() -> None:
    tags = _classify(
        "Exile target creature you control, then return it to the battlefield under your control."
    )
    assert "blink" in tags


# ── mill ──────────────────────────────────────────────────────────────────────


def test_mill_keyword() -> None:
    tags = _classify("Mill 3.")
    assert "mill" in tags


# ── protection ────────────────────────────────────────────────────────────────


def test_protection_hexproof_in_text() -> None:
    tags = _classify("This creature has hexproof.")
    assert "protection" in tags


def test_protection_indestructible_keyword() -> None:
    tags = _classify("", keywords=["Indestructible"])
    assert "protection" in tags


# ── extra turn ────────────────────────────────────────────────────────────────


def test_extra_turn() -> None:
    tags = _classify("Take an extra turn after this one.")
    assert "extra_turn" in tags


# ── land destruction ──────────────────────────────────────────────────────────


def test_land_destruction() -> None:
    tags = _classify("Destroy target land.")
    assert "land_destruction" in tags


# ── tribal ────────────────────────────────────────────────────────────────────


def test_tribal_type_line() -> None:
    tags = _classify("", type_line="Tribal Instant — Goblin")
    assert "tribal" in tags


# ── vanilla card ─────────────────────────────────────────────────────────────


def test_vanilla_card_no_tags() -> None:
    tags = _classify("", type_line="Creature — Beast")
    assert tags == []


# ── classify_traits ───────────────────────────────────────────────────────────


def test_traits_etb_oracle_text() -> None:
    traits = classify_traits("When this creature enters the battlefield, draw a card.", [])
    assert "etb" in traits


def test_traits_etb_short_pattern() -> None:
    traits = classify_traits("When ~ enters, you gain 2 life.", [])
    assert "etb" in traits


def test_traits_activated_tap_cost() -> None:
    traits = classify_traits("{T}: Draw a card.", [])
    assert "activated" in traits


def test_traits_activated_mana_cost() -> None:
    traits = classify_traits("{2}: Put a +1/+1 counter on this creature.", [])
    assert "activated" in traits


def test_traits_evasion_flying_keyword() -> None:
    traits = classify_traits("", ["Flying"])
    assert "evasion" in traits


def test_traits_evasion_menace_keyword() -> None:
    traits = classify_traits("", ["Menace"])
    assert "evasion" in traits


def test_traits_evasion_cant_be_blocked() -> None:
    traits = classify_traits("This creature can't be blocked.", [])
    assert "evasion" in traits


def test_traits_no_traits_vanilla() -> None:
    traits = classify_traits("", [])
    assert traits == []


def test_traits_multiple_traits() -> None:
    traits = classify_traits(
        "When ~ enters the battlefield, draw a card. {T}: Add {G}.", ["Flying"]
    )
    assert "etb" in traits
    assert "activated" in traits
    assert "evasion" in traits


# ── classify_token_types ──────────────────────────────────────────────────────


def test_token_types_treasure() -> None:
    result = classify_token_types("Create a Treasure token.")
    assert result == ["treasure"]


def test_token_types_food() -> None:
    result = classify_token_types("Create a Food token.")
    assert result == ["food"]


def test_token_types_clue() -> None:
    result = classify_token_types("Investigate. (Create a Clue token.)")
    assert result == ["clue"]


def test_token_types_blood() -> None:
    result = classify_token_types("Create a Blood token.")
    assert result == ["blood"]


def test_token_types_powerstone() -> None:
    result = classify_token_types("Create a tapped Powerstone token.")
    assert result == ["powerstone"]


def test_token_types_map() -> None:
    result = classify_token_types("Create a Map token.")
    assert result == ["map"]


def test_token_types_incubator() -> None:
    result = classify_token_types("Create an Incubator token.")
    assert result == ["incubator"]


def test_token_types_multiple() -> None:
    result = classify_token_types(
        "Create a Treasure token. When this creature dies, create a Food token."
    )
    assert "treasure" in result
    assert "food" in result


def test_token_types_no_match() -> None:
    result = classify_token_types("Destroy target creature.")
    assert result == []


def test_token_types_empty_text() -> None:
    result = classify_token_types(None)
    assert result == []


def test_token_types_zombie() -> None:
    result = classify_token_types("Create a 2/2 black Zombie creature token.")
    assert result == ["zombie"]


def test_token_types_squirrel() -> None:
    result = classify_token_types("Create two 1/1 green Squirrel creature tokens.")
    assert result == ["squirrel"]


def test_token_types_elf() -> None:
    result = classify_token_types("Create a 1/1 green Elf creature token.")
    assert result == ["elf"]


def test_token_types_creature_and_artifact() -> None:
    result = classify_token_types(
        "Create a Treasure token. Create a 2/2 black Zombie creature token."
    )
    assert "treasure" in result
    assert "zombie" in result
