"""Bounded, immutable normalized source payloads; no community enrichment."""

import gzip
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from mtg_helper.services.recommendations.refinement import parse_rules
from mtg_helper.services.recommendations.source import Card, Catalog, build_catalog

MAX_BYTES = 130 * 1024 * 1024
RULES_HASH = "8d860e451f20f38865b725b42d82feb714c725373dd8f3b32b8652b3eeb070ca"
RULES_URL = "https://media.wizards.com/2026/downloads/MagicCompRules%2020260925.txt"
RULES_PATH = Path(__file__).parent / "data" / "rules-20260925.txt"


class SourceFace(BaseModel):
    name: str = Field(min_length=1)
    mana_cost: str | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None


class SourceCard(SourceFace):
    oracle_id: UUID
    cmc: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    color_identity: list[str]
    legalities: dict[str, str]
    keywords: list[str] = Field(default_factory=list)
    games: list[str] = Field(default_factory=list)
    layout: str | None = None
    card_faces: list[SourceFace] = Field(default_factory=list)
    border_color: str | None = None
    security_stamp: str | None = None
    set_type: str | None = None

    @model_validator(mode="after")
    def printed_type(self) -> "SourceCard":
        first_type = self.card_faces[0].type_line if self.card_faces else self.type_line
        if not first_type:
            raise ValueError("Missing first printed type line; source eligibility is unknown")
        return self


def normalize_cards(cards: list[Card]) -> list[Card]:
    """Preserve printed root/face boundaries and source characteristics, never semantic tags."""
    indexed = {}
    for raw in cards:
        if not raw.get("oracle_id"):
            continue
        identity = str(UUID(str(raw["oracle_id"])))
        if identity in indexed:
            raise ValueError(
                f"Duplicate Oracle source identity {identity}; retain last-good catalog"
            )
        item = SourceCard.model_validate(raw).model_dump(mode="json", exclude_unset=True)
        item["card_faces"] = item.get("card_faces", [])
        indexed[identity] = item
    return [indexed[key] for key in sorted(indexed)]


def pack(value: Any) -> tuple[bytes, str]:
    """Hash normalized UTF-8 bytes and compress deterministically for durable source storage."""
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(data) > MAX_BYTES:
        raise ValueError("Normalized source exceeds 130 MiB; retain last-good catalog")
    return gzip.compress(data, mtime=0), hashlib.sha256(data).hexdigest()


def unpack(blob: bytes, expected: str) -> Any:
    """Bound decompression and verify exact source identity before loading JSON."""
    with gzip.GzipFile(fileobj=io.BytesIO(blob)) as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Source size/hash mismatch; restore the immutable snapshot")
    return json.loads(data)


@dataclass(kw_only=True)
class Sources:
    card_hash: str
    rules_hash: str
    cards: dict[str, Card]
    catalog: Catalog
    rules: Card

    @classmethod
    def load(cls, *, cards: list[Card], rules: Card, card_hash: str, rules_hash: str) -> "Sources":
        return cls(
            card_hash=card_hash,
            rules_hash=rules_hash,
            cards={c["oracle_id"]: c for c in cards},
            catalog=build_catalog(cards),
            rules=rules,
        )


def packaged_rules() -> tuple[bytes, str]:
    """Load the pinned complete official resource; no request or workstation-cache dependency."""
    raw = RULES_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != RULES_HASH:
        raise ValueError("Packaged official rules hash mismatch; Discover is unavailable")
    return pack(parse_rules(raw.decode("utf-8-sig")))
