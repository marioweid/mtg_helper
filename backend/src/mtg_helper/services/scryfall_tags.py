"""Canonical Oracle tags and direct memberships from Scryfall's gzip JSONL export."""

import gzip
import io
import zlib
from collections import deque
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

MAX_TAG_BYTES = 64 * 1024 * 1024
MAX_TAG_LINE_BYTES = 2 * 1024 * 1024
MAX_TAG_RECORDS = 20_000
MAX_HIERARCHY_RELATIONS = 100_000
MAX_EXPANDED_MEMBERSHIPS = 2_000_000


class OracleTagging(BaseModel):
    """One direct source membership; source weight is not a contextual fit score."""

    model_config = ConfigDict(extra="allow")

    oracle_id: UUID
    weight: str = Field(min_length=1)
    annotation: str | None = None


class OracleTag(BaseModel):
    """Source identity, metadata, hierarchy, and original direct memberships."""

    model_config = ConfigDict(extra="allow")

    object: Literal["tag"]
    type: Literal["oracle"]
    id: UUID
    slug: str = Field(min_length=1)
    label: str = Field(min_length=1)
    uri: str = Field(min_length=1)
    description: str | None
    aliases: list[str]
    parent_ids: list[UUID]
    child_ids: list[UUID]
    taggings: list[OracleTagging]


class OracleTagCatalog:
    """Keep direct source labels distinct from descendant-aware query expansions."""

    def __init__(self, tags: list[OracleTag]) -> None:
        if not tags or len(tags) > MAX_TAG_RECORDS:
            raise ValueError("Scryfall Oracle-tag record count is empty or exceeds limits")
        self.tags: dict[UUID, OracleTag] = {}
        self.slugs: dict[str, UUID] = {}
        self.descendants: dict[UUID, set[UUID]] = {}
        self.memberships: dict[UUID, set[UUID]] = {}
        for tag in tags:
            self._add(tag)
        self._validate_edges()
        self._expand()

    @classmethod
    def from_records(cls, rows: list[dict[str, Any]]) -> "OracleTagCatalog":
        """Validate every record, retaining extra source fields rather than discarding them."""
        tags = []
        for number, row in enumerate(rows, 1):
            try:
                tags.append(OracleTag.model_validate(row))
            except ValidationError as exc:
                raise ValueError(f"Invalid Scryfall Oracle-tag record at line {number}") from exc
        return cls(tags)

    def _add(self, tag: OracleTag) -> None:
        if tag.id in self.tags or tag.slug in self.slugs:
            raise ValueError(f"Duplicate Scryfall tag {tag.id}/{tag.slug}; retain last-good tags")
        direct = {membership.oracle_id for membership in tag.taggings}
        if len(direct) != len(tag.taggings):
            raise ValueError(f"Duplicate Oracle membership in tag {tag.id}; inspect the export")
        self.tags[tag.id] = tag
        self.slugs[tag.slug] = tag.id
        self.descendants[tag.id] = {tag.id}
        self.memberships[tag.id] = direct

    def _validate_edges(self) -> None:
        for tag in self.tags.values():
            self._validate_references(tag.id, tag.parent_ids, "child_ids")
            self._validate_references(tag.id, tag.child_ids, "parent_ids")

    def _validate_references(self, identity: UUID, references: list[UUID], reciprocal: str) -> None:
        if len(set(references)) != len(references):
            raise ValueError(f"Duplicate hierarchy reference for Scryfall tag {identity}")
        for reference in references:
            if reference not in self.tags:
                raise ValueError(f"Missing hierarchy reference {reference} for tag {identity}")
            if identity not in getattr(self.tags[reference], reciprocal):
                raise ValueError(f"Nonreciprocal hierarchy edge for Scryfall tag {identity}")

    def _expand(self) -> None:
        # Bottom-up traversal avoids recursive stack limits on upstream hierarchies.
        pending = {key: len(tag.child_ids) for key, tag in self.tags.items()}
        ready = deque(key for key, count in pending.items() if count == 0)
        visited = 0
        relations = len(self.tags)
        memberships = sum(map(len, self.memberships.values()))
        if relations > MAX_HIERARCHY_RELATIONS or memberships > MAX_EXPANDED_MEMBERSHIPS:
            raise ValueError("Scryfall Oracle-tag expansion exceeds limits; retain tags")
        while ready:
            child = ready.popleft()
            visited += 1
            for parent in self.tags[child].parent_ids:
                relations -= len(self.descendants[parent])
                memberships -= len(self.memberships[parent])
                self.descendants[parent].update(self.descendants[child])
                self.memberships[parent].update(self.memberships[child])
                relations += len(self.descendants[parent])
                memberships += len(self.memberships[parent])
                if relations > MAX_HIERARCHY_RELATIONS or memberships > MAX_EXPANDED_MEMBERSHIPS:
                    raise ValueError("Scryfall Oracle-tag expansion exceeds limits; retain tags")
                pending[parent] -= 1
                if pending[parent] == 0:
                    ready.append(parent)
        if visited != len(self.tags):
            raise ValueError("Cycle in Scryfall tag hierarchy; retain last-good tags")

    def members(self, identity: UUID) -> set[UUID]:
        """Resolve a canonical UUID, including descendants without rewriting source taggings.

        Args:
            identity: Scryfall tag UUID, not a slug, alias, or locally inferred role.

        Returns:
            A copy of matching Oracle identities.

        Raises:
            ValueError: If the requested UUID is absent from the source generation.
        """
        if identity not in self.tags:
            raise ValueError(f"Unknown Scryfall tag {identity}; refresh or correct the query")
        return self.memberships[identity].copy()

    def records(self) -> list[dict[str, Any]]:
        """Return deterministic source records with direct memberships and annotations intact."""
        result = []
        for identity in sorted(self.tags):
            row = self.tags[identity].model_dump(mode="json", exclude_unset=True)
            row["taggings"].sort(key=lambda member: member["oracle_id"])
            row["parent_ids"].sort()
            row["child_ids"].sort()
            result.append(row)
        return result


def _parse_tag_line(line: bytes, number: int) -> OracleTag:
    try:
        return OracleTag.model_validate_json(line)
    except ValidationError as exc:
        raise ValueError(f"Invalid Scryfall Oracle-tag record at line {number}") from exc


def parse_tags(content: bytes) -> OracleTagCatalog:
    """Validate a bounded gzip JSONL Oracle-tag export; artwork/partial records fail visibly.

    Args:
        content: Compressed source bytes, capped independently from decompressed content.

    Returns:
        A validated direct/expanded Oracle-tag index.

    Raises:
        ValueError: For malformed, empty, oversized, or inconsistent source data.
    """
    if len(content) > MAX_TAG_BYTES:
        raise ValueError("Scryfall Oracle-tag archive exceeds 64 MiB; retain last-good tags")
    tags = []
    size = number = 0
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            while line := stream.readline(MAX_TAG_LINE_BYTES + 1):
                number += 1
                size += len(line)
                if len(line) > MAX_TAG_LINE_BYTES or size > MAX_TAG_BYTES:
                    raise ValueError("Scryfall Oracle-tag JSONL exceeds size limits")
                if not line.strip():
                    continue
                tags.append(_parse_tag_line(line, number))
                if len(tags) > MAX_TAG_RECORDS:
                    raise ValueError("Scryfall Oracle-tag record count exceeds limits")
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("Invalid Scryfall Oracle-tag gzip JSONL; retain last-good tags") from exc
    if not tags:
        raise ValueError("Empty Scryfall Oracle-tag export; retain last-good tags")
    return OracleTagCatalog(tags)
