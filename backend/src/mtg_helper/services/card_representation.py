"""Structured card representation helpers.

This module builds deterministic card feature payloads used by embedding and
future scoring work. It keeps card facts explicit instead of relying only on
free-form oracle text.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class CardRepresentation:
    """Structured card features plus a labeled embedding text view."""

    name: str
    type_line: str | None
    oracle_text: str | None
    color_identity: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    card_types: list[str] = field(default_factory=list)
    subtypes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    traits: list[str] = field(default_factory=list)
    token_types: list[str] = field(default_factory=list)
    mana_value: float | None = None
    edhrec_rank: int | None = None

    def feature_payload(self) -> dict[str, object]:
        """Return compact structured features for storage/search payloads."""
        return {
            "color_identity": self.color_identity,
            "mana_value": self.mana_value,
            "keywords": self.keywords,
            "card_types": self.card_types,
            "subtypes": self.subtypes,
            "tags": self.tags,
            "traits": self.traits,
            "token_types": self.token_types,
            "edhrec_rank": self.edhrec_rank,
        }

    def feature_labels(self) -> list[str]:
        """Flatten high-signal categorical features into stable labels."""
        labels: list[str] = []
        labels.extend(f"color:{value}" for value in self.color_identity)
        labels.extend(f"keyword:{value.lower()}" for value in self.keywords)
        labels.extend(f"type:{value.lower()}" for value in self.card_types)
        labels.extend(f"subtype:{value.lower()}" for value in self.subtypes)
        labels.extend(f"tag:{value}" for value in self.tags)
        labels.extend(f"trait:{value}" for value in self.traits)
        labels.extend(f"token:{value}" for value in self.token_types)
        if self.mana_value is not None:
            labels.append(f"mana_value:{_mana_bucket(self.mana_value)}")
        return labels

    def embedding_text(self) -> str:
        """Return a labeled text representation for document embeddings."""
        parts = [f"Name: {self.name}"]
        _append(parts, "Type line", self.type_line)
        _append(parts, "Oracle text", self.oracle_text)
        _append_joined(parts, "Color identity", self.color_identity)
        if self.mana_value is not None:
            parts.append(f"Mana value: {self.mana_value:g}")
        _append_joined(parts, "Card types", self.card_types)
        _append_joined(parts, "Subtypes", self.subtypes)
        _append_joined(parts, "Keywords", self.keywords)
        _append_joined(parts, "Commander role tags", self.tags)
        _append_joined(parts, "Mechanical traits", self.traits)
        _append_joined(parts, "Produces tokens", self.token_types)
        if self.edhrec_rank is not None:
            parts.append(f"EDHREC rank: {self.edhrec_rank}")
        return " | ".join(parts)


def from_card_fields(
    *,
    name: str,
    type_line: str | None,
    oracle_text: str | None,
    color_identity: list[str] | None = None,
    keywords: list[str] | None = None,
    card_types: list[str] | None = None,
    subtypes: list[str] | None = None,
    tags: list[str] | None = None,
    traits: list[str] | None = None,
    token_types: list[str] | None = None,
    mana_value: Decimal | float | int | None = None,
    edhrec_rank: int | None = None,
) -> CardRepresentation:
    """Build a card representation from DB or pipeline fields."""
    return CardRepresentation(
        name=name,
        type_line=type_line,
        oracle_text=oracle_text,
        color_identity=_dedupe(color_identity),
        keywords=_dedupe(keywords),
        card_types=_dedupe(card_types),
        subtypes=_dedupe(subtypes),
        tags=_dedupe(tags),
        traits=_dedupe(traits),
        token_types=_dedupe(token_types),
        mana_value=_coerce_float(mana_value),
        edhrec_rank=edhrec_rank,
    )


def from_row(row: Any) -> CardRepresentation:
    """Build a card representation from an asyncpg-style row."""
    return from_card_fields(
        name=row["name"],
        type_line=row["type_line"],
        oracle_text=row["oracle_text"],
        color_identity=list(row["color_identity"] or []),
        keywords=list(row["keywords"] or []),
        card_types=list(row["card_types"] or []),
        subtypes=list(row["subtypes"] or []),
        tags=list(row["tags"] or []),
        traits=list(row["traits"] or []),
        token_types=list(row["token_types"] or []),
        mana_value=row["cmc"],
        edhrec_rank=row["edhrec_rank"],
    )


def build_embedding_text(
    *,
    name: str,
    type_line: str | None,
    oracle_text: str | None,
    keywords: list[str],
    color_identity: list[str] | None = None,
    card_types: list[str] | None = None,
    subtypes: list[str] | None = None,
    tags: list[str] | None = None,
    traits: list[str] | None = None,
    token_types: list[str] | None = None,
    mana_value: Decimal | float | int | None = None,
    edhrec_rank: int | None = None,
) -> str:
    """Build labeled embedding text from raw card fields."""
    return from_card_fields(
        name=name,
        type_line=type_line,
        oracle_text=oracle_text,
        color_identity=color_identity,
        keywords=keywords,
        card_types=card_types,
        subtypes=subtypes,
        tags=tags,
        traits=traits,
        token_types=token_types,
        mana_value=mana_value,
        edhrec_rank=edhrec_rank,
    ).embedding_text()


def _dedupe(values: list[str] | None) -> list[str]:
    if not values:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _coerce_float(value: Decimal | float | int | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _mana_bucket(value: float) -> str:
    if value <= 1:
        return "0-1"
    if value <= 3:
        return "2-3"
    if value <= 5:
        return "4-5"
    return "6+"


def _append(parts: list[str], label: str, value: str | None) -> None:
    if value:
        parts.append(f"{label}: {value}")


def _append_joined(parts: list[str], label: str, values: list[str]) -> None:
    if values:
        parts.append(f"{label}: {', '.join(values)}")
