"""Offline release/evidence gates; no database, network, or paid model calls."""

import gzip
import io
import json
from datetime import date
from uuid import uuid4

import httpx
import pytest

from mtg_helper.services.new_cards import catalog
from mtg_helper.services.new_cards.discovery import card_facts, paper_card, release_history
from mtg_helper.services.new_cards.evaluator import EvidenceRequest, fingerprint
from mtg_helper.services.new_cards.repository import price_cents

pytestmark = pytest.mark.no_db


def printing(**changes):
    return {
        "object": "card",
        "oracle_id": str(uuid4()),
        "name": "Example",
        "games": ["paper"],
        "layout": "normal",
        "set_type": "expansion",
        "released_at": "2026-09-01",
        "reprint": False,
        "oracle_text": "Draw a card.",
        **changes,
    }


def test_main_release_ignores_early_promo_and_late_representative():
    main = printing()
    promo = main | {"promo": True, "released_at": "2026-07-01"}
    reprint = main | {"released_at": "2026-10-01", "reprint": True}
    history = release_history([reprint, promo, main])[main["oracle_id"]]
    assert history.first_paper == date(2026, 7, 1)
    assert history.release == date(2026, 9, 1)


@pytest.mark.parametrize(
    "changes",
    [
        {"set_type": "promo"},
        {"set_type": "funny"},
        {"reprint": True},
        {"released_at": None},
        {"set_type": "box"},
        {"set_type": "from_the_vault"},
    ],
)
def test_unknown_or_reprinted_origin_is_excluded(changes):
    card = printing(**changes)
    assert release_history([card])[card["oracle_id"]].release is None


def test_older_special_original_does_not_become_new_in_regular_product():
    main = printing()
    old = main | {"set_type": "box", "released_at": "2020-01-01"}
    assert release_history([main, old])[main["oracle_id"]].release is None


@pytest.mark.parametrize(
    "changes",
    [
        {"oracle_id": None},
        {"games": ["arena"]},
        {"layout": "token"},
        {"border_color": "gold"},
        {"border_color": "silver"},
        {"security_stamp": "acorn"},
        {"type_line": "Conspiracy"},
        {"set_type": "memorabilia"},
    ],
)
def test_nonplayable_shapes_are_excluded(changes):
    assert not paper_card(printing(**changes))
    assert not release_history([printing(**changes)])


def test_faces_preserve_numeric_source_and_access_boundaries():
    facts = card_facts(
        printing(
            card_faces=[
                {
                    "name": "Front",
                    "type_line": "Creature",
                    "oracle_text": "Flying",
                    "toughness": "3",
                },
                {"name": "Back", "type_line": "Land", "oracle_text": "Add one mana."},
            ]
        )
    )
    assert facts.faces[0].toughness == "3"
    assert "Back [Land]: Add one mana." in facts.oracle_text


def request():
    physical = card_facts(printing(name="Support")).model_dump(mode="json")
    physical["pending_cut"] = True
    return EvidenceRequest(
        {"physical": [physical]}, [card_facts(printing()).model_dump(mode="json")]
    )


def judgment():
    return {
        "C01": {
            "label": "strong",
            "reason": "Useful interaction",
            "caveat": "Needs testing",
            "required_changes": [],
            "evidence": [
                {"key": key, "field": "oracle_text", "face_index": None, "quote": "Draw a card."}
                for key in ("C01", "D00")
            ],
        }
    }


def test_identity_binding_and_pending_cut_warning():
    item = request().decode(json.dumps(judgment()))[0]
    assert [e.name for e in item.evidence] == ["Example", "Support"]
    assert "Pending cuts remove cited support: Support." in item.caveat
    assert request().schema()["required"] == ["C01"]


@pytest.mark.parametrize("case", ["missing", "foreign", "invented", "face", "changes", "support"])
def test_invalid_evidence_fails_whole_batch(case):
    data = judgment()
    if case == "missing":
        data = {}
    elif case == "foreign":
        data["C01"]["evidence"][1]["key"] = "C02"
    elif case == "invented":
        data["C01"]["evidence"][0]["quote"] = "Destroy all creatures."
    elif case == "face":
        data["C01"]["evidence"][0]["face_index"] = 2
    elif case == "changes":
        data["C01"]["required_changes"] = ["Add another card"]
    else:
        data["C01"]["evidence"].pop()
    with pytest.raises(ValueError):
        request().decode(json.dumps(data))


def test_duplicate_json_keys_and_oversized_context_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        request().decode('{"C01": {}, "C01": {}}')
    req = request()
    req.context["notes"] = "x" * 180_001
    with pytest.raises(ValueError, match="180 KB"):
        req.payload()


def test_fingerprints_order_independent_but_content_sensitive():
    assert fingerprint({"a": 1, "b": 2}) == fingerprint({"b": 2, "a": 1})
    assert fingerprint({"a": 1}) != fingerprint({"a": 2})


@pytest.mark.parametrize(
    "price,expected", [(None, None), ("NaN", None), ("-1", None), ("0.15", 15), ("bad", None)]
)
def test_price_unknown_is_not_zero(price, expected):
    assert price_cents(json.dumps({"eur": price})) == expected


@pytest.mark.parametrize("raw", [None, "null", "[]", "invalid"])
def test_missing_or_malformed_price_container(raw):
    assert price_cents(raw) is None


@pytest.mark.parametrize("body", [b"bad", gzip.compress(b"[]"), gzip.compress(b"{}")])
def test_invalid_archives_fail_without_partial_catalog(body):
    with pytest.raises((ValueError, gzip.BadGzipFile)):
        list(catalog._records(io.BytesIO(body)))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["small", "large", "network", "host"])
async def test_history_download_failure_bounds(mode, monkeypatch):
    body = gzip.compress((json.dumps(printing()) + "\n").encode())
    if mode == "large":
        monkeypatch.setattr(catalog, "_MAX_BYTES", 1)
    status = 503 if mode == "network" else 200
    transport = httpx.MockTransport(lambda _: httpx.Response(status, content=body))
    url = "https://untrusted.example/file" if mode == "host" else "https://data.scryfall.io/file"
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises((ValueError, httpx.HTTPStatusError)):
            await catalog.download_history(client, url)
