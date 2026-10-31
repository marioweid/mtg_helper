"""Closed, globally bounded model choices decoded into unchanged saved source searches."""

import json
from enum import StrEnum
from types import GenericAlias
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, create_model, model_validator

from mtg_helper.services.recommendations import term_queries
from mtg_helper.services.recommendations.discovery import StrictModel
from mtg_helper.services.recommendations.refinement import unique_object
from mtg_helper.services.recommendations.source import Card

PROMPT = (
    term_queries.PROMPT
    + """
First select the shared oracle_tag_ids and printed_keywords lists, each containing at most eight
unique supplied values. Select only terms used by your searches; reuse a choice without adding
it again. Exact source values are enumerated in the response schema; do not paraphrase them.
Each search group contains oracle_tag_indices and printed_keyword_indices: ZERO-BASED indices
into those shared selected lists, NOT indices into the input catalog and NOT UUIDs or keywords.
Every index must refer to an existing selected choice. For example, with two selected tags, only
indices 0 and 1 exist. A group must use at least one tag or keyword index. OR within each group,
AND across groups; all queries are alternatives. Leave an unavailable or unused source kind as [].
Keep purpose and card_types_any in each query. Do not include raw term values in query groups.
"""
)

ChoiceIndex = Annotated[int, Field(strict=True, ge=0, le=7)]


class SelectionGroup(StrictModel):
    oracle_tag_indices: list[ChoiceIndex] = Field(max_length=8)
    printed_keyword_indices: list[ChoiceIndex] = Field(max_length=8)

    @model_validator(mode="after")
    def nonempty(self) -> Self:
        if not self.oracle_tag_indices and not self.printed_keyword_indices:
            raise ValueError("Every source group must reference a selected term")
        return self


def _choice_field(name: str, values: list[str]) -> tuple[Any, Any]:
    # Empty enums are invalid JSON Schema; maxItems=0 closes an unavailable source kind instead.
    if not values:
        return list[str], Field(max_length=0)
    # Distinct source-kind names keep the two enum definitions unambiguous in JSON Schema.
    choices = StrEnum(
        name,  # ty: ignore[mismatched-type-name] -- The class name depends on the source kind.
        {f"choice_{index}": value for index, value in enumerate(values)},
    )
    return GenericAlias(list, choices), Field(max_length=8)


def selection_type(payload: Card) -> type[BaseModel]:
    """Build the provider and validator contract from the exact frozen source menu.

    Args:
        payload: Source-backed setup payload containing Oracle tags and printed keywords.

    Returns:
        A strict response model with catalog-enumerated global choices and indexed searches.

    Raises:
        ValueError: Neither source kind is available; no useful request can be made.
    """
    tags = [str(tag["id"]) for tag in payload["oracle_tags"]]
    words = payload["printed_keywords"]
    if not tags and not words:
        raise ValueError("No source terms available; sync Scryfall sources before requesting terms")
    query = create_model(
        "SelectedQuery",
        __base__=term_queries.StrategyQuery,
        groups=(list[SelectionGroup], Field(min_length=1, max_length=2)),
    )
    return create_model(
        "TermSelection",
        __base__=StrictModel,
        oracle_tag_ids=_choice_field("OracleTagChoice", tags),
        printed_keywords=_choice_field("PrintedKeywordChoice", words),
        queries=(GenericAlias(list, query), Field(min_length=1, max_length=6)),
    )


def _referenced(values: list[str], indices: list[int]) -> list[str]:
    if any(index >= len(values) for index in indices):
        raise ValueError("Search index does not reference an existing selected term")
    if len(indices) != len(set(indices)):
        raise ValueError("Search group repeats a selected-term index")
    return [values[index] for index in indices]


def _decode(selection: Card) -> Card:
    for field in ("oracle_tag_ids", "printed_keywords"):
        if len(selection[field]) != len(set(selection[field])):
            raise ValueError("Global source choices must be unique; reuse their indices instead")
    queries = []
    for query in selection["queries"]:
        groups = [
            {
                "oracle_tag_ids": _referenced(
                    selection["oracle_tag_ids"], group["oracle_tag_indices"]
                ),
                "printed_keywords": _referenced(
                    selection["printed_keywords"], group["printed_keyword_indices"]
                ),
            }
            for group in query["groups"]
        ]
        queries.append(query | {"groups": groups})
    return {"queries": queries}


class Workflow(term_queries.Workflow):
    """Hide indexed provider choices behind the existing source-query workflow interface."""

    def accept(self, phase: str, text: str, data: Card) -> Card:
        """Validate a closed selection, then apply all persisted-query/source guards unchanged.

        Args:
            phase: The single supported setup phase, `plan`.
            text: Raw response JSON; duplicate properties and invalid references are errors.
            data: Workflow state passed through the existing acceptance interface.

        Returns:
            Grouped source searches with the frozen strategy revision and source hash.
        """
        payload = self.payload(phase, data)
        selection = selection_type(payload).model_validate(
            json.loads(text, object_pairs_hook=unique_object)
        )
        decoded = _decode(selection.model_dump(mode="json"))
        return super().accept(phase, json.dumps(decoded), data)
